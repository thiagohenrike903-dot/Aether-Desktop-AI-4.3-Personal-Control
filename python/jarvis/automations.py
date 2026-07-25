"""Bounded local automations with simulation and execution history."""
from __future__ import annotations

import asyncio
import json
import operator
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from . import operations, os_control, safety_mode, workspace
from .config import settings
from .executor import assess_risk

ExecuteCallback = Callable[
    [dict[str, Any], bool, str | None, bool],
    Awaitable[dict[str, Any]],
]

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "automations.sqlite3"
_TRIGGER_TYPES = {"manual", "schedule", "file", "event", "condition"}
_COMPARATORS = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS automations (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    trigger_json       TEXT NOT NULL,
    action_json        TEXT NOT NULL,
    enabled            INTEGER NOT NULL DEFAULT 0,
    require_approval   INTEGER NOT NULL DEFAULT 1,
    watch_supported    INTEGER NOT NULL DEFAULT 1,
    runtime_json       TEXT NOT NULL DEFAULT '{}',
    next_run_at        REAL,
    last_triggered_at  REAL,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_automations_enabled
ON automations(enabled, next_run_at);
CREATE TABLE IF NOT EXISTS automation_runs (
    id             TEXT PRIMARY KEY,
    automation_id  TEXT NOT NULL,
    state          TEXT NOT NULL,
    operation_id   TEXT,
    trigger_json   TEXT NOT NULL,
    triggered_at   REAL NOT NULL,
    finished_at    REAL,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS ix_automation_runs
ON automation_runs(automation_id, triggered_at DESC);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.commit()


_init_db()


def _parse_run_at(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        raise ValueError("O gatilho schedule exige run_at ou interval_seconds.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("run_at precisa estar em ISO 8601.") from exc
    if parsed.tzinfo is None:
        # Local desktop time is the honest interpretation of an offset-less
        # value; the UI should send an offset for unambiguous scheduling.
        return parsed.timestamp()
    return parsed.timestamp()


def _bind_workspace_path(raw_path: Any) -> tuple[str, str]:
    root = workspace.get_root()
    if root is None:
        raise ValueError("Selecione um workspace para usar gatilhos de arquivo.")
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("O caminho do arquivo é obrigatório.")
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.expanduser().resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("O gatilho de arquivo precisa ficar no workspace.") from exc
    else:
        resolved = (root / candidate).resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("O gatilho de arquivo precisa ficar no workspace.") from exc
    return str(root), relative.as_posix()


def _normalize_trigger(trigger: dict[str, Any]) -> tuple[dict[str, Any], bool, float | None]:
    item = dict(trigger or {})
    trigger_type = str(item.get("type") or "manual").strip().lower()
    if trigger_type not in _TRIGGER_TYPES:
        raise ValueError("Tipo de gatilho inválido.")
    item["type"] = trigger_type
    next_run_at: float | None = None
    watch_supported = True
    if trigger_type == "schedule":
        if item.get("interval_seconds") is not None:
            interval = int(item["interval_seconds"])
            if interval < 60:
                raise ValueError("O intervalo mínimo é 60 segundos.")
            item["interval_seconds"] = interval
            next_run_at = time.time() + interval
        else:
            next_run_at = _parse_run_at(item.get("run_at"))
            item["run_at"] = next_run_at
    elif trigger_type == "file":
        workspace_root, relative_path = _bind_workspace_path(item.get("path"))
        event = str(item.get("event") or "modified").lower()
        if event not in {"modified", "created", "deleted", "exists"}:
            raise ValueError("Evento de arquivo inválido.")
        item = {
            "type": "file",
            "workspace_root": workspace_root,
            "path": relative_path,
            "event": event,
        }
    elif trigger_type == "event":
        name = str(item.get("name") or "").strip().lower()
        if not name or not re.fullmatch(r"[a-z0-9_.:-]{1,120}", name):
            raise ValueError("Nome de evento inválido.")
        item = {"type": "event", "name": name}
    elif trigger_type == "condition":
        condition = str(item.get("condition") or "").lower()
        if condition == "file_exists":
            workspace_root, relative_path = _bind_workspace_path(item.get("path"))
            item = {
                "type": "condition",
                "condition": "file_exists",
                "workspace_root": workspace_root,
                "path": relative_path,
                "expected": bool(item.get("expected", True)),
            }
        elif condition in {"cpu_percent", "memory_percent"}:
            comparator = str(item.get("operator") or "gte").lower()
            if comparator not in _COMPARATORS:
                raise ValueError("Operador de condição inválido.")
            threshold = float(item.get("threshold"))
            if not 0 <= threshold <= 100:
                raise ValueError("O limiar deve ficar entre 0 e 100.")
            item = {
                "type": "condition",
                "condition": condition,
                "operator": comparator,
                "threshold": threshold,
            }
        else:
            watch_supported = False
            item = {
                "type": "condition",
                "condition": condition or "unsupported",
            }
    return item, watch_supported, next_run_at


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "trigger": json.loads(row["trigger_json"]),
        "action": json.loads(row["action_json"]),
        "enabled": bool(row["enabled"]),
        "require_approval": bool(row["require_approval"]),
        "watch_supported": bool(row["watch_supported"]),
        "next_run_at": row["next_run_at"],
        "last_triggered_at": row["last_triggered_at"],
        "run_count": row["run_count"] if "run_count" in row.keys() else 0,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create(
    *,
    name: str,
    trigger: dict[str, Any],
    action: dict[str, Any],
    enabled: bool = False,
    require_approval: bool = True,
) -> dict[str, Any]:
    name = str(name or "").strip()
    if not name:
        raise ValueError("O nome da automação é obrigatório.")
    if not isinstance(action, dict) or not action.get("type"):
        raise ValueError("A ação estruturada é obrigatória.")
    normalized, supported, next_run_at = _normalize_trigger(trigger)
    automation_id = str(uuid.uuid4())
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO automations (
                id, name, trigger_json, action_json, enabled,
                require_approval, watch_supported, runtime_json,
                next_run_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?, ?)
            """,
            (
                automation_id,
                name[:240],
                json.dumps(normalized, ensure_ascii=False),
                json.dumps(action, ensure_ascii=False),
                int(enabled and supported),
                int(require_approval),
                int(supported),
                next_run_at,
                now,
                now,
            ),
        )
        connection.commit()
    item = get(automation_id)
    assert item is not None
    return item


def get(automation_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT a.*, COUNT(r.id) AS run_count
            FROM automations a
            LEFT JOIN automation_runs r ON r.automation_id = a.id
            WHERE a.id = ?
            GROUP BY a.id
            """,
            (automation_id,),
        ).fetchone()
    return _public(row) if row else None


def list_automations(*, enabled: bool | None = None) -> list[dict[str, Any]]:
    where = "" if enabled is None else "WHERE enabled = ?"
    values: list[Any] = [] if enabled is None else [int(enabled)]
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT a.*, COUNT(r.id) AS run_count
            FROM automations a
            LEFT JOIN automation_runs r ON r.automation_id = a.id
            {where.replace('enabled', 'a.enabled')}
            GROUP BY a.id
            ORDER BY a.updated_at DESC
            """,
            values,
        ).fetchall()
    return [_public(row) for row in rows]


def update(automation_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get(automation_id)
    if current is None:
        raise KeyError(automation_id)
    clean: dict[str, Any] = {}
    if "name" in changes:
        name = str(changes["name"] or "").strip()
        if not name:
            raise ValueError("O nome da automação é obrigatório.")
        clean["name"] = name[:240]
    if "action" in changes:
        action = changes["action"]
        if not isinstance(action, dict) or not action.get("type"):
            raise ValueError("A ação estruturada é obrigatória.")
        clean["action_json"] = json.dumps(action, ensure_ascii=False)
    supported = current["watch_supported"]
    if "trigger" in changes:
        trigger, supported, next_run_at = _normalize_trigger(changes["trigger"])
        clean["trigger_json"] = json.dumps(trigger, ensure_ascii=False)
        clean["watch_supported"] = int(supported)
        clean["next_run_at"] = next_run_at
        clean["runtime_json"] = "{}"
        if not supported:
            clean["enabled"] = 0
    if "require_approval" in changes:
        clean["require_approval"] = int(bool(changes["require_approval"]))
    if "enabled" in changes:
        clean["enabled"] = int(bool(changes["enabled"]) and supported)
    if clean:
        assignments = ", ".join(f"{field} = ?" for field in clean)
        with _LOCK, _connect() as connection:
            connection.execute(
                f"UPDATE automations SET {assignments}, updated_at = ? WHERE id = ?",
                [*clean.values(), time.time(), automation_id],
            )
            connection.commit()
    item = get(automation_id)
    assert item is not None
    return item


def delete(automation_id: str) -> bool:
    with _LOCK, _connect() as connection:
        connection.execute(
            "DELETE FROM automation_runs WHERE automation_id = ?",
            (automation_id,),
        )
        result = connection.execute(
            "DELETE FROM automations WHERE id = ?",
            (automation_id,),
        )
        connection.commit()
    return result.rowcount > 0


async def _condition_value(trigger: dict[str, Any]) -> tuple[bool, Any]:
    condition = trigger.get("condition")
    if condition == "file_exists":
        root = Path(str(trigger["workspace_root"])).resolve()
        candidate = (root / str(trigger["path"])).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return False, None
        value = candidate.exists()
        return value == bool(trigger.get("expected", True)), value
    snapshot = await os_control.system_snapshot()
    if condition == "cpu_percent":
        value = float(snapshot["cpu"])
    elif condition == "memory_percent":
        value = float(snapshot["memory"])
    else:
        return False, None
    comparison = _COMPARATORS[str(trigger.get("operator") or "gte")]
    return comparison(value, float(trigger["threshold"])), value


async def simulate(automation_id: str) -> dict[str, Any]:
    item = get(automation_id)
    if item is None:
        raise KeyError(automation_id)
    suspension = safety_mode.get_suspension("automations")
    trigger = item["trigger"]
    trigger_type = trigger["type"]
    would_run = False
    reason = ""
    observed: Any = None
    if not item["watch_supported"]:
        reason = "Este tipo de gatilho não é suportado pelo núcleo atual."
    elif trigger_type == "manual":
        would_run = True
        reason = "A execução manual pode ser iniciada."
    elif trigger_type == "schedule":
        would_run = bool(item["next_run_at"] and item["next_run_at"] <= time.time())
        reason = "Horário atingido." if would_run else "O horário ainda não foi atingido."
    elif trigger_type == "event":
        reason = "Aguardando o evento autenticado correspondente."
    elif trigger_type == "file":
        root = Path(trigger["workspace_root"]).resolve()
        candidate = (root / trigger["path"]).resolve()
        exists = candidate.exists()
        observed = {"exists": exists}
        would_run = trigger["event"] == "exists" and exists
        reason = (
            "O arquivo existe."
            if would_run
            else "Mudanças são avaliadas pelo polling; a simulação não as fabrica."
        )
    elif trigger_type == "condition":
        would_run, observed = await _condition_value(trigger)
        reason = "Condição satisfeita." if would_run else "Condição não satisfeita."
    risk = assess_risk(item["action"])
    trigger_would_run = would_run
    safety = safety_mode.preview(item["action"], confirmed=False)
    if safety["blocked"]:
        would_run = False
        reason = f"{reason} {safety['reason']}".strip()
    if suspension["suspended"]:
        would_run = False
        reason = (
            f"{reason} Automações suspensas: "
            f"{suspension['reason'] or 'suspensão global ativa.'}"
        ).strip()
    return {
        "would_run": would_run,
        "trigger_would_run": trigger_would_run,
        "requires_approval": bool(
            item["require_approval"]
            or risk != "low"
            or safety["requires_confirmation"]
        ),
        "affected": operations.affected_resources(item["action"]),
        "risk": risk,
        "reason": reason,
        "observed": observed,
        "side_effects": False,
        "safety": safety,
        "suspension": suspension,
    }


def _new_run(automation_id: str, trigger: dict[str, Any]) -> str:
    run_id = str(uuid.uuid4())
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO automation_runs (
                id, automation_id, state, operation_id,
                trigger_json, triggered_at
            ) VALUES (?, ?, 'running', NULL, ?, ?)
            """,
            (
                run_id,
                automation_id,
                json.dumps(
                    operations.safe_payload(trigger),
                    ensure_ascii=False,
                    default=str,
                ),
                time.time(),
            ),
        )
        connection.commit()
    return run_id


async def run(
    automation_id: str,
    execute_callback: ExecuteCallback,
    *,
    trigger_context: dict[str, Any] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    item = get(automation_id)
    if item is None:
        raise KeyError(automation_id)
    suspension = safety_mode.get_suspension("automations")
    if suspension["suspended"]:
        return {
            "id": None,
            "automation_id": automation_id,
            "state": "failed",
            "operation_id": None,
            "trigger": operations.safe_payload(
                trigger_context or {"type": "manual"}
            ),
            "triggered_at": None,
            "finished_at": time.time(),
            "error": (
                "Automação não iniciada porque a suspensão global está ativa."
            ),
            "suspended": True,
            "suspension": suspension,
        }
    context = trigger_context or {"type": "manual"}
    run_id = _new_run(automation_id, context)
    safety = safety_mode.preview(item["action"], confirmed=confirmed)
    if safety["blocked"]:
        error = f"Automação bloqueada pelo modo seguro: {safety['reason']}"
        now = time.time()
        with _LOCK, _connect() as connection:
            connection.execute(
                """
                UPDATE automation_runs
                SET state = 'failed', finished_at = ?, error = ?
                WHERE id = ?
                """,
                (now, error, run_id),
            )
            connection.execute(
                """
                UPDATE automations
                SET last_triggered_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, automation_id),
            )
            connection.commit()
        return get_run(run_id) or {
            "id": run_id,
            "state": "failed",
            "error": error,
        }
    try:
        operation = await execute_callback(
            item["action"],
            confirmed,
            f"automation-{run_id}",
            bool(item["require_approval"] or safety["requires_confirmation"]),
        )
        state = operation.get("state") or "failed"
        operation_id = operation.get("id")
        finished_at = time.time() if state in operations.TERMINAL_STATES else None
        error = operation.get("error")
    except Exception as exc:
        state = "failed"
        operation_id = None
        finished_at = time.time()
        error = str(exc)
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE automation_runs
            SET state = ?, operation_id = ?, finished_at = ?, error = ?
            WHERE id = ?
            """,
            (state, operation_id, finished_at, error, run_id),
        )
        connection.execute(
            "UPDATE automations SET last_triggered_at = ?, updated_at = ? WHERE id = ?",
            (time.time(), time.time(), automation_id),
        )
        connection.commit()
    return get_run(run_id) or {"id": run_id, "state": state}


def get_run(run_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM automation_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    state = row["state"]
    error = row["error"]
    finished_at = row["finished_at"]
    if row["operation_id"]:
        operation = operations.get(row["operation_id"])
        if operation:
            state = operation["state"]
            error = operation["error"]
            finished_at = operation["finished_at"]
            if state != row["state"] or finished_at != row["finished_at"]:
                with _LOCK, _connect() as connection:
                    connection.execute(
                        """
                        UPDATE automation_runs
                        SET state = ?, error = ?, finished_at = ?
                        WHERE id = ?
                        """,
                        (state, error, finished_at, run_id),
                    )
                    connection.commit()
    return {
        "id": row["id"],
        "automation_id": row["automation_id"],
        "state": state,
        "operation_id": row["operation_id"],
        "trigger": json.loads(row["trigger_json"]),
        "triggered_at": row["triggered_at"],
        "finished_at": finished_at,
        "error": error,
    }


def list_runs(automation_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    if get(automation_id) is None:
        raise KeyError(automation_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT id FROM automation_runs
            WHERE automation_id = ?
            ORDER BY triggered_at DESC
            LIMIT ?
            """,
            (automation_id, max(1, min(int(limit), 500))),
        ).fetchall()
    return [item for row in rows if (item := get_run(row["id"])) is not None]


def _file_fingerprint(trigger: dict[str, Any]) -> dict[str, Any]:
    root = Path(trigger["workspace_root"]).resolve()
    candidate = (root / trigger["path"]).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return {"exists": False, "invalid": True}
    try:
        stat = candidate.stat()
        return {
            "exists": True,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
    except OSError:
        return {"exists": False}


async def _poll_one(item: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    trigger = item["trigger"]
    trigger_type = trigger["type"]
    now = time.time()
    if trigger_type == "schedule":
        return bool(item["next_run_at"] and item["next_run_at"] <= now), {
            "type": "schedule",
            "scheduled_at": item["next_run_at"],
        }
    if trigger_type == "condition":
        matched, observed = await _condition_value(trigger)
        with _LOCK, _connect() as connection:
            row = connection.execute(
                "SELECT runtime_json FROM automations WHERE id = ?",
                (item["id"],),
            ).fetchone()
            previous = json.loads(row["runtime_json"] or "{}") if row else {}
            connection.execute(
                "UPDATE automations SET runtime_json = ? WHERE id = ?",
                (
                    json.dumps({"matched": matched, "observed": observed}),
                    item["id"],
                ),
            )
            connection.commit()
        return bool(matched and not previous.get("matched", False)), {
            "type": "condition",
            "condition": trigger["condition"],
            "observed": observed,
        }
    if trigger_type != "file":
        return False, {}
    current = _file_fingerprint(trigger)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT runtime_json FROM automations WHERE id = ?",
            (item["id"],),
        ).fetchone()
        previous = json.loads(row["runtime_json"] or "{}") if row else {}
        connection.execute(
            "UPDATE automations SET runtime_json = ? WHERE id = ?",
            (json.dumps(current), item["id"]),
        )
        connection.commit()
    if not previous:
        return False, {
            "type": "file",
            "event": "baseline",
            "current": current,
        }
    event = trigger["event"]
    matched = (
        (event == "created" and not previous.get("exists") and current.get("exists"))
        or (event == "deleted" and previous.get("exists") and not current.get("exists"))
        or (
            event == "modified"
            and previous.get("exists")
            and current.get("exists")
            and (
                previous.get("mtime_ns") != current.get("mtime_ns")
                or previous.get("size") != current.get("size")
            )
        )
        or (
            event == "exists"
            and not previous.get("exists")
            and current.get("exists", False)
        )
    )
    return bool(matched), {
        "type": "file",
        "event": event,
        "previous": previous,
        "current": current,
    }


def _advance_schedule(item: dict[str, Any]) -> None:
    trigger = item["trigger"]
    next_run_at: float | None = None
    enabled = item["enabled"]
    if trigger["type"] == "schedule":
        interval = trigger.get("interval_seconds")
        if interval:
            next_run_at = time.time() + int(interval)
        else:
            enabled = False
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE automations
            SET next_run_at = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_run_at, int(enabled), time.time(), item["id"]),
        )
        connection.commit()


async def poll(execute_callback: ExecuteCallback) -> list[dict[str, Any]]:
    if safety_mode.is_suspended("automations"):
        return []
    triggered: list[dict[str, Any]] = []
    for item in list_automations(enabled=True):
        if not item["watch_supported"] or item["trigger"]["type"] in {"manual", "event"}:
            continue
        matched, context = await _poll_one(item)
        if matched:
            triggered.append(
                await run(item["id"], execute_callback, trigger_context=context)
            )
            if item["trigger"]["type"] == "schedule":
                _advance_schedule(item)
    return triggered


async def emit_event(
    event_name: str,
    execute_callback: ExecuteCallback,
    *,
    payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if safety_mode.is_suspended("automations"):
        return []
    normalized = str(event_name or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.:-]{1,120}", normalized):
        raise ValueError("Nome de evento inválido.")
    runs: list[dict[str, Any]] = []
    safe_payload = operations.safe_payload(dict(payload or {}))
    for item in list_automations(enabled=True):
        trigger = item["trigger"]
        if trigger["type"] == "event" and trigger["name"] == normalized:
            runs.append(
                await run(
                    item["id"],
                    execute_callback,
                    trigger_context={
                        "type": "event",
                        "name": normalized,
                        "payload": safe_payload,
                    },
                )
            )
    return runs


async def scheduler_loop(
    execute_callback: ExecuteCallback,
    *,
    poll_seconds: float = 2.0,
) -> None:
    while True:
        try:
            await poll(execute_callback)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One polling failure must not stop future local automations.
            pass
        await asyncio.sleep(max(1.0, poll_seconds))
