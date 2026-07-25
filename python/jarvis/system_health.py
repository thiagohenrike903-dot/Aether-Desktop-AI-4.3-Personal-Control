"""Local component health checks with a persistent, redacted history."""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from . import (
    automations,
    connections,
    operations,
    project_library,
    safety_mode,
)
from .config import settings

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS health_checks (
    id            TEXT PRIMARY KEY,
    purpose       TEXT NOT NULL,
    status        TEXT NOT NULL,
    summary_json  TEXT NOT NULL,
    created_at    REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    import json

    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _database_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for path in sorted(settings.data_dir.glob("*.sqlite3"))[:30]:
        try:
            uri = f"file:{path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
            result = connection.execute("PRAGMA quick_check").fetchone()
            connection.close()
            ok = bool(result and result[0] == "ok")
            detail = str(result[0] if result else "sem resultado")[:500]
        except (OSError, sqlite3.Error) as exc:
            ok = False
            detail = type(exc).__name__
        checks.append({
            "id": f"database:{path.name}",
            "component": "storage",
            "name": path.name,
            "status": "healthy" if ok else "error",
            "detail": detail,
            "repair": None if ok else {
                "id": "restore_from_backup",
                "reversible": True,
                "automatic": False,
            },
        })
    return checks


def _automation_check() -> dict[str, Any]:
    items = automations.list_automations(enabled=None)
    repeated: list[dict[str, Any]] = []
    for item in items:
        runs = automations.list_runs(item["id"], limit=5)
        recent_states = [run.get("state") for run in runs]
        failures = 0
        for state in recent_states:
            if state != "failed":
                break
            failures += 1
        if failures >= 3:
            repeated.append({
                "id": item["id"],
                "name": item["name"],
                "consecutive_failures": failures,
                "last_error": str(runs[0].get("error") or "")[:500] if runs else None,
            })
    suspended = safety_mode.get_suspension("automations")
    status = "warning" if repeated or suspended["suspended"] else "healthy"
    return {
        "id": "automations",
        "component": "automations",
        "name": "Automações",
        "status": status,
        "detail": (
            f"{len(repeated)} automação(ões) falhando repetidamente."
            if repeated
            else (
                "Execução suspensa pelo modo seguro."
                if suspended["suspended"]
                else "Nenhuma falha repetida detectada."
            )
        ),
        "items": repeated,
        "suspension": suspended,
        "repair": None,
    }


def _operation_check() -> dict[str, Any]:
    recent = operations.list_operations(limit=100)
    failures = [
        item for item in recent
        if item["state"] == "failed" and item["updated_at"] >= time.time() - 86_400
    ]
    by_kind = Counter(item["kind"] for item in failures)
    repeated = [
        {"kind": kind, "failures_24h": count}
        for kind, count in by_kind.most_common()
        if count >= 3
    ]
    return {
        "id": "operations",
        "component": "control_center",
        "name": "Operações",
        "status": "warning" if repeated else "healthy",
        "detail": (
            f"{len(repeated)} tipo(s) com falhas repetidas nas últimas 24 horas."
            if repeated else "Nenhum padrão de falha repetida detectado."
        ),
        "items": repeated,
        "repair": None,
    }


def _library_check() -> dict[str, Any]:
    stale: list[dict[str, Any]] = []
    for project in project_library.list_projects(archived=None, limit=200):
        status = (
            project_library.index_status(project["id"])
            if hasattr(project_library, "index_status")
            else {"stale_documents": [], "status": "ready"}
        )
        for item in status.get("stale_documents", []):
            stale.append({"project_id": project["id"], **item})
    return {
        "id": "library",
        "component": "library",
        "name": "Índice da biblioteca",
        "status": "warning" if stale else "healthy",
        "detail": (
            f"{len(stale)} documento(s) precisam de reindexação."
            if stale else "Índices locais atualizados."
        ),
        "items": stale[:100],
        "repair": (
            {"id": "reindex_project", "reversible": True, "automatic": False}
            if stale else None
        ),
    }


def _connections_check() -> dict[str, Any]:
    overview = connections.overview()
    active_id = overview["active_profile_id"]
    active = next(
        (item for item in overview["profiles"] if item["id"] == active_id),
        None,
    )
    ready = bool(active and active["configured"])
    return {
        "id": "connections",
        "component": "connections",
        "name": "Modelo ativo",
        "status": "healthy" if ready else "warning",
        "detail": (
            f"{active['name']} configurado."
            if ready else "O modelo ativo ainda não está disponível."
        ),
        "active_profile": active,
        "repair": None,
    }


def check(*, purpose: str = "manual") -> dict[str, Any]:
    purpose = str(purpose or "manual").strip().lower()[:80]
    storage_ok = settings.data_dir.exists() and os.access(settings.data_dir, os.W_OK)
    disk = shutil.disk_usage(settings.data_dir)
    checks: list[dict[str, Any]] = [
        {
            "id": "storage",
            "component": "storage",
            "name": "Armazenamento local",
            "status": "healthy" if storage_ok and disk.free >= 100 * 1024 * 1024 else "error",
            "detail": (
                f"{round(disk.free / (1024 ** 3), 2)} GB livres."
                if storage_ok else "A pasta local não permite gravação."
            ),
            "repair": None,
        },
        *_database_checks(),
        _connections_check(),
        _automation_check(),
        _operation_check(),
        _library_check(),
        {
            "id": "plugins",
            "component": "plugins",
            "name": "Plugins",
            "status": (
                "warning" if safety_mode.is_suspended("plugins") else "healthy"
            ),
            "detail": (
                "Execução suspensa pelo modo seguro."
                if safety_mode.is_suspended("plugins")
                else "Componente disponível; plugins continuam sendo código confiável."
            ),
            "repair": None,
        },
    ]
    counts = Counter(item["status"] for item in checks)
    status = "error" if counts["error"] else ("warning" if counts["warning"] else "healthy")
    check_id = str(uuid.uuid4())
    created_at = time.time()
    summary = {
        "total": len(checks),
        "healthy": counts["healthy"],
        "warning": counts["warning"],
        "error": counts["error"],
    }
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO health_checks (id, purpose, status, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (check_id, purpose, status, _json(summary), created_at),
        )
        connection.commit()
    return {
        "ok": status != "error",
        "id": check_id,
        "purpose": purpose,
        "status": status,
        "summary": summary,
        "checks": checks,
        "created_at": created_at,
        "preflight_passed": status != "error",
    }


def history(*, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM health_checks
            ORDER BY created_at DESC LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "purpose": row["purpose"],
            "status": row["status"],
            "summary": _loads(row["summary_json"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def repair(repair_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    """Run only explicitly reversible repairs."""
    if repair_id == "reindex_project":
        if not project_id:
            raise ValueError("Informe o projeto que deve ser reindexado.")
        if not hasattr(project_library, "reindex_project"):
            return {
                "ok": False,
                "available": False,
                "error": "A reindexação incremental não está disponível.",
            }
        result = project_library.reindex_project(project_id)
        return {
            "ok": True,
            "repair_id": repair_id,
            "reversible": True,
            "result": result,
        }
    raise ValueError("Reparo desconhecido ou não automático.")


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.commit()


_init_db()
