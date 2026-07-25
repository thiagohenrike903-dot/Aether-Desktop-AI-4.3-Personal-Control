"""Side-effect-free simulations that can become versioned workflows."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import operations, permissions, safety_mode, workflows, workspace
from .config import settings
from .executor import assess_risk

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS simulations (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    project_id       TEXT,
    steps_json       TEXT NOT NULL,
    result_json      TEXT NOT NULL,
    state_hash       TEXT NOT NULL,
    approved         INTEGER NOT NULL DEFAULT 0,
    converted_id     TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_simulations_created
ON simulations(created_at DESC);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    ).hexdigest()


def _file_state(path_value: str) -> dict[str, Any] | None:
    root = workspace.get_root()
    if root is None:
        return None
    try:
        root_path = Path(root).resolve()
        path = Path(path_value).expanduser().resolve()
        path.relative_to(root_path)
    except (OSError, ValueError):
        return None
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "kind": "directory" if path.is_dir() else "file",
        "size": stat.st_size if path.is_file() else None,
        "modified_ns": stat.st_mtime_ns,
    }


def create(
    *,
    name: str,
    steps: list[dict[str, Any]],
    project_id: str | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()[:160]
    if not clean_name:
        raise ValueError("O nome da simulação é obrigatório.")
    if not isinstance(steps, list) or not steps or len(steps) > 30:
        raise ValueError("Informe entre 1 e 30 etapas.")
    template = workflows.prepare_template(steps)
    clean_steps = template["steps"]
    rendered: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    state_before: list[dict[str, Any]] = []
    blocked = 0
    for index, raw in enumerate(clean_steps):
        action = raw.get("action") if isinstance(raw, dict) else None
        if not isinstance(action, dict):
            raise ValueError(f"A etapa {index + 1} não possui uma ação.")
        kind = safety_mode.action_kind(action)
        if not kind:
            raise ValueError(f"A etapa {index + 1} não informa um tipo de ação.")
        risk = assess_risk(action)
        safety = safety_mode.preview(action, confirmed=False, project_id=project_id)
        permission = permissions.decision(
            f"action:{kind}",
            risk=risk,
            confirmed=False,
            project_id=project_id,
        )
        is_blocked = bool(safety["blocked"] or permission == "block")
        needs_approval = bool(
            safety["requires_confirmation"] or permission == "ask"
        )
        blocked += int(is_blocked)
        affected = operations.affected_resources(action)
        for resource in affected:
            if resource.get("type") == "file" and resource.get("path"):
                state = _file_state(str(resource["path"]))
                if state and state not in state_before:
                    state_before.append(state)
        if needs_approval:
            approvals.append({
                "step_id": str(raw.get("id") or f"step-{index + 1}"),
                "scope": f"action:{kind}",
                "risk": risk,
                "affected": affected,
            })
        rendered.append({
            "id": str(raw.get("id") or f"step-{index + 1}")[:80],
            "name": str(raw.get("name") or kind.replace("_", " ").title())[:160],
            "action": operations.safe_payload(action),
            "affected": affected,
            "risk": risk,
            "permission": permission,
            "safety": safety,
            "blocked": is_blocked,
            "requires_approval": needs_approval,
        })
    result = {
        "side_effects": False,
        "steps": rendered,
        "variables": template["variables"],
        "state_before": state_before,
        "approvals": approvals,
        "blocked_steps": blocked,
        "ready": blocked == 0,
    }
    simulation_id = str(uuid.uuid4())
    state_hash = _hash({
        "project_id": project_id,
        "steps": clean_steps,
        "state_before": state_before,
    })
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO simulations
                (id, name, project_id, steps_json, result_json, state_hash,
                 approved, converted_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
            """,
            (
                simulation_id, clean_name, project_id, _json(clean_steps),
                _json(result), state_hash, now, now,
            ),
        )
        connection.commit()
    item = get(simulation_id)
    assert item is not None
    return item


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "project_id": row["project_id"],
        "steps": _loads(row["steps_json"], []),
        "result": _loads(row["result_json"], {}),
        "state_hash": row["state_hash"],
        "approved": bool(row["approved"]),
        "converted_workflow_id": row["converted_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get(simulation_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM simulations WHERE id = ?", (simulation_id,)
        ).fetchone()
    return _public(row) if row else None


def list_simulations(*, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM simulations ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_public(row) for row in rows]


def approve(simulation_id: str, *, state_hash: str) -> dict[str, Any]:
    item = get(simulation_id)
    if item is None:
        raise KeyError(simulation_id)
    if not item["result"].get("ready"):
        raise ValueError("A simulação possui etapas bloqueadas.")
    if str(state_hash) != item["state_hash"]:
        raise ValueError("O estado da simulação mudou; execute-a novamente.")
    current_state: list[dict[str, Any]] = []
    for previous in item["result"].get("state_before", []):
        if not isinstance(previous, dict) or not previous.get("path"):
            continue
        refreshed = _file_state(str(previous["path"]))
        if refreshed is not None:
            current_state.append(refreshed)
    current_hash = _hash({
        "project_id": item["project_id"],
        "steps": item["steps"],
        "state_before": current_state,
    })
    if current_hash != item["state_hash"]:
        raise ValueError(
            "Um recurso afetado mudou desde a prévia; execute a simulação novamente."
        )
    with _LOCK, _connect() as connection:
        connection.execute(
            "UPDATE simulations SET approved = 1, updated_at = ? WHERE id = ?",
            (time.time(), simulation_id),
        )
        connection.commit()
    approved = get(simulation_id)
    assert approved is not None
    return approved


def convert_to_workflow(
    simulation_id: str,
    *,
    workflow_name: str | None = None,
) -> dict[str, Any]:
    item = get(simulation_id)
    if item is None:
        raise KeyError(simulation_id)
    if not item["approved"]:
        raise ValueError("A simulação precisa ser aprovada antes da conversão.")
    if item["converted_workflow_id"]:
        existing = workflows.get_workflow(item["converted_workflow_id"])
        if existing:
            return existing
    workflow = workflows.create_workflow(
        name=str(workflow_name or item["name"])[:160],
        description=f"Criado a partir da simulação {simulation_id[:8]}.",
        steps=item["steps"],
        variables=(
            item["result"].get("variables")
            if isinstance(item["result"].get("variables"), list)
            else []
        ),
        enabled=False,
    )
    with _LOCK, _connect() as connection:
        connection.execute(
            "UPDATE simulations SET converted_id = ?, updated_at = ? WHERE id = ?",
            (workflow["id"], time.time(), simulation_id),
        )
        connection.commit()
    return workflow


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        connection.commit()


_init_db()
