"""Versioned, reusable workflow templates with side-effect-free previews."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import operations, permissions, safety_mode
from .config import settings
from .executor import assess_risk
from .redaction import is_sensitive_field, redact_text

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_VARIABLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z][A-Za-z0-9_]{0,63})\}")
_VALUE_TYPES = {"string", "number", "integer", "boolean", "path", "url"}
_MAX_STEPS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL,
    steps_json     TEXT NOT NULL,
    variables_json TEXT NOT NULL,
    enabled        INTEGER NOT NULL DEFAULT 1,
    version        INTEGER NOT NULL DEFAULT 1,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_revisions (
    id             TEXT PRIMARY KEY,
    workflow_id    TEXT NOT NULL,
    version        INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL,
    created_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_revisions
ON workflow_revisions(workflow_id, version DESC);
CREATE TABLE IF NOT EXISTS workflow_runs (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    workflow_version INTEGER NOT NULL,
    state           TEXT NOT NULL,
    simulation      INTEGER NOT NULL DEFAULT 0,
    input_json      TEXT NOT NULL,
    result_json     TEXT,
    operation_ids_json TEXT NOT NULL,
    started_at      REAL NOT NULL,
    finished_at     REAL
);
CREATE INDEX IF NOT EXISTS ix_workflow_runs
ON workflow_runs(workflow_id, started_at DESC);
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


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _secret_value(value: str) -> bool:
    return redact_text(value) != value


def _sanitize_template_value(
    value: Any,
    *,
    discovered: set[str],
    depth: int = 0,
) -> Any:
    if depth > 6:
        raise ValueError("O template excede o limite de profundidade.")
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key).strip()[:120]
            if not key:
                continue
            if is_sensitive_field(key):
                variable = re.sub(r"[^A-Za-z0-9_]", "_", key).strip("_")
                variable = (variable or "secret")[:64]
                if not variable[0].isalpha():
                    variable = f"secret_{variable}"[:64]
                discovered.add(variable)
                output[key] = f"${{{variable}}}"
                continue
            output[key] = _sanitize_template_value(
                item,
                discovered=discovered,
                depth=depth + 1,
            )
        return output
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("Uma lista do workflow excede 100 itens.")
        return [
            _sanitize_template_value(
                item,
                discovered=discovered,
                depth=depth + 1,
            )
            for item in value
        ]
    if isinstance(value, str):
        text = value[:20_000]
        for name in _PLACEHOLDER.findall(text):
            discovered.add(name)
        if _secret_value(text):
            raise ValueError(
                "O workflow contém uma credencial. Use uma variável sem valor padrão."
            )
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2_000]


def _sanitize_variables(
    value: Any,
    *,
    discovered: set[str],
) -> list[dict[str, Any]]:
    supplied = value if isinstance(value, list) else []
    by_name: dict[str, dict[str, Any]] = {}
    for raw in supplied[:100]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not _VARIABLE.fullmatch(name):
            raise ValueError(f"Variável inválida: {name or '(vazia)'}")
        value_type = str(raw.get("type") or "string").lower()
        if value_type not in _VALUE_TYPES:
            raise ValueError(f"Tipo inválido para a variável {name}.")
        secret = bool(raw.get("secret"))
        default = raw.get("default")
        if secret and default not in (None, ""):
            raise ValueError("Variáveis secretas não podem possuir valor padrão.")
        if isinstance(default, str) and _secret_value(default):
            raise ValueError("Um valor padrão parece conter uma credencial.")
        by_name[name] = {
            "name": name,
            "label": str(raw.get("label") or name)[:120],
            "type": value_type,
            "required": raw.get("required") is not False,
            "secret": secret,
            "default": None if secret else default,
            "description": str(raw.get("description") or "")[:500],
        }
    for name in sorted(discovered):
        if name not in by_name:
            by_name[name] = {
                "name": name,
                "label": name.replace("_", " ").strip().title(),
                "type": "string",
                "required": True,
                "secret": any(token in name.lower() for token in ("key", "token", "secret", "password")),
                "default": None,
                "description": "Variável detectada automaticamente no template.",
            }
    return list(by_name.values())


def _sanitize_steps(value: Any) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("O workflow precisa ter pelo menos uma etapa.")
    if len(value) > _MAX_STEPS:
        raise ValueError(f"O workflow aceita no máximo {_MAX_STEPS} etapas.")
    output: list[dict[str, Any]] = []
    discovered: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"Etapa {index + 1} inválida.")
        action = raw.get("action")
        if not isinstance(action, dict):
            raise ValueError(f"Etapa {index + 1} não possui uma ação.")
        clean_action = _sanitize_template_value(action, discovered=discovered)
        kind = safety_mode.action_kind(clean_action)
        if not kind:
            raise ValueError(f"Etapa {index + 1} não informou um tipo de ação válido.")
        output.append({
            "id": str(raw.get("id") or f"step-{index + 1}")[:80],
            "name": str(raw.get("name") or kind.replace("_", " ").title())[:160],
            "action": clean_action,
            "continue_on_error": bool(raw.get("continue_on_error", False)),
        })
    return output, discovered


def prepare_template(
    steps: list[dict[str, Any]],
    variables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a persistable workflow template without retaining credentials.

    Simulations and operation conversion use this public boundary so every
    stored action follows the same placeholder, validation and size rules as a
    workflow created directly by the user.
    """
    clean_steps, discovered = _sanitize_steps(steps)
    clean_variables = _sanitize_variables(variables, discovered=discovered)
    return {"steps": clean_steps, "variables": clean_variables}


def _snapshot_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "description": item["description"],
        "steps": item["steps"],
        "variables": item["variables"],
        "enabled": item["enabled"],
        "version": item["version"],
    }


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "steps": _loads(row["steps_json"], []),
        "variables": _loads(row["variables_json"], []),
        "enabled": bool(row["enabled"]),
        "version": int(row["version"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def list_workflows(*, enabled: bool | None = None, limit: int = 200) -> list[dict[str, Any]]:
    where = "" if enabled is None else "WHERE enabled = ?"
    values: list[Any] = [] if enabled is None else [int(enabled)]
    values.append(max(1, min(int(limit), 500)))
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM workflows {where} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [_public(row) for row in rows]


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()
    return _public(row) if row else None


def create_workflow(
    *,
    name: str,
    description: str = "",
    steps: list[dict[str, Any]],
    variables: list[dict[str, Any]] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()[:160]
    if not clean_name:
        raise ValueError("O nome do workflow é obrigatório.")
    prepared = prepare_template(steps, variables)
    clean_steps = prepared["steps"]
    clean_variables = prepared["variables"]
    workflow_id = str(uuid.uuid4())
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO workflows (
                id, name, description, steps_json, variables_json,
                enabled, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                workflow_id,
                clean_name,
                str(description or "")[:4_000],
                _json(clean_steps),
                _json(clean_variables),
                int(bool(enabled)),
                now,
                now,
            ),
        )
        connection.commit()
    item = get_workflow(workflow_id)
    assert item is not None
    return item


def _save_revision(connection: sqlite3.Connection, item: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO workflow_revisions
            (id, workflow_id, version, snapshot_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            item["id"],
            item["version"],
            _json(_snapshot_payload(item)),
            time.time(),
        ),
    )


def update_workflow(workflow_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get_workflow(workflow_id)
    if current is None:
        raise KeyError(workflow_id)
    name = (
        str(changes.get("name") or "").strip()[:160]
        if "name" in changes
        else current["name"]
    )
    if not name:
        raise ValueError("O nome do workflow é obrigatório.")
    steps_source = changes.get("steps", current["steps"])
    clean_steps, discovered = _sanitize_steps(steps_source)
    clean_variables = _sanitize_variables(
        changes.get("variables", current["variables"]),
        discovered=discovered,
    )
    next_version = int(current["version"]) + 1
    with _LOCK, _connect() as connection:
        _save_revision(connection, current)
        connection.execute(
            """
            UPDATE workflows
            SET name = ?, description = ?, steps_json = ?, variables_json = ?,
                enabled = ?, version = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name,
                str(changes.get("description", current["description"]))[:4_000],
                _json(clean_steps),
                _json(clean_variables),
                int(bool(changes.get("enabled", current["enabled"]))),
                next_version,
                time.time(),
                workflow_id,
            ),
        )
        connection.commit()
    item = get_workflow(workflow_id)
    assert item is not None
    return item


def delete_workflow(workflow_id: str) -> bool:
    with _LOCK, _connect() as connection:
        result = connection.execute(
            "DELETE FROM workflows WHERE id = ?",
            (workflow_id,),
        )
        connection.commit()
    return result.rowcount > 0


def list_revisions(workflow_id: str) -> list[dict[str, Any]]:
    if get_workflow(workflow_id) is None:
        raise KeyError(workflow_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, version, snapshot_json, created_at
            FROM workflow_revisions
            WHERE workflow_id = ?
            ORDER BY version DESC, created_at DESC
            LIMIT 100
            """,
            (workflow_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "version": int(row["version"]),
            "snapshot": _loads(row["snapshot_json"], {}),
            "created_at": float(row["created_at"]),
        }
        for row in rows
    ]


def restore_revision(workflow_id: str, revision_id: str) -> dict[str, Any]:
    current = get_workflow(workflow_id)
    if current is None:
        raise KeyError(workflow_id)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT snapshot_json FROM workflow_revisions
            WHERE id = ? AND workflow_id = ?
            """,
            (revision_id, workflow_id),
        ).fetchone()
    if row is None:
        raise KeyError(revision_id)
    snapshot = _loads(row["snapshot_json"], {})
    return update_workflow(
        workflow_id,
        {
            "name": snapshot.get("name", current["name"]),
            "description": snapshot.get("description", current["description"]),
            "steps": snapshot.get("steps", current["steps"]),
            "variables": snapshot.get("variables", current["variables"]),
            "enabled": snapshot.get("enabled", current["enabled"]),
        },
    )


def _coerce_value(spec: dict[str, Any], value: Any) -> Any:
    value_type = spec["type"]
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "sim"}:
            return True
        if lowered in {"0", "false", "no", "não", "nao"}:
            return False
        raise ValueError(f"{spec['label']} precisa ser verdadeiro ou falso.")
    if value_type == "integer":
        return int(value)
    if value_type == "number":
        return float(value)
    text = str(value)
    if value_type == "url":
        from urllib.parse import urlparse

        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"{spec['label']} precisa ser uma URL HTTP(S).")
    if value_type == "path" and ("\x00" in text or len(text) > 2_000):
        raise ValueError(f"{spec['label']} contém um caminho inválido.")
    return text[:20_000]


def resolve_inputs(
    workflow: dict[str, Any],
    supplied: dict[str, Any] | None,
) -> dict[str, Any]:
    source = supplied if isinstance(supplied, dict) else {}
    output: dict[str, Any] = {}
    for spec in workflow["variables"]:
        name = spec["name"]
        value = source.get(name, spec.get("default"))
        if value in (None, "") and spec["required"]:
            raise ValueError(f"A variável {spec['label']} é obrigatória.")
        if value in (None, ""):
            output[name] = value
            continue
        output[name] = _coerce_value(spec, value)
    return output


def _render(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, variables) for item in value]
    if not isinstance(value, str):
        return value
    match = _PLACEHOLDER.fullmatch(value)
    if match:
        return variables.get(match.group(1))
    return _PLACEHOLDER.sub(
        lambda found: str(variables.get(found.group(1), "")),
        value,
    )


def materialize(
    workflow_id: str,
    *,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve typed variables while keeping secret values memory-only."""
    workflow = get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(workflow_id)
    if not workflow["enabled"]:
        raise ValueError("Ative o workflow antes de executá-lo.")
    resolved = resolve_inputs(workflow, values)
    steps: list[dict[str, Any]] = []
    for item in workflow["steps"]:
        action = _render(item["action"], resolved)
        if not isinstance(action, dict):
            raise ValueError("Uma ação renderizada deixou de ser um objeto.")
        steps.append({
            "id": item["id"],
            "name": item["name"],
            "action": action,
            "continue_on_error": item["continue_on_error"],
        })
    return {
        "workflow": workflow,
        "inputs": resolved,
        "steps": steps,
    }


def preview(
    workflow_id: str,
    *,
    values: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(workflow_id)
    resolved = resolve_inputs(workflow, values)
    steps: list[dict[str, Any]] = []
    approval_count = 0
    blocked_count = 0
    for item in workflow["steps"]:
        action = _render(item["action"], resolved)
        if not isinstance(action, dict):
            raise ValueError("Uma ação renderizada deixou de ser um objeto.")
        kind = safety_mode.action_kind(action)
        risk = assess_risk(action)
        safety = safety_mode.preview(
            action,
            confirmed=False,
            project_id=project_id,
        )
        permission = permissions.decision(
            f"action:{kind}",
            risk=risk,
            confirmed=False,
            project_id=project_id,
        )
        blocked = safety["blocked"] or permission == "block"
        requires_approval = safety["requires_confirmation"] or permission == "ask"
        blocked_count += int(blocked)
        approval_count += int(requires_approval)
        steps.append({
            "id": item["id"],
            "name": item["name"],
            "kind": kind,
            "action": operations.safe_payload(action),
            "affected": operations.affected_resources(action),
            "safety": safety,
            "permission": permission,
            "blocked": blocked,
            "requires_approval": requires_approval,
            "continue_on_error": item["continue_on_error"],
        })
    state = {
        "workflow_id": workflow_id,
        "workflow_version": workflow["version"],
        "project_id": project_id,
        "steps": steps,
    }
    return {
        "ok": True,
        "simulation": True,
        "side_effects": False,
        "workflow": {
            "id": workflow["id"],
            "name": workflow["name"],
            "version": workflow["version"],
        },
        "steps": steps,
        "approvals_required": approval_count,
        "blocked_steps": blocked_count,
        "ready": blocked_count == 0,
        "state_hash": _canonical_hash(state),
        "resolved_inputs": {
            spec["name"]: ("[fornecido]" if spec["secret"] and resolved.get(spec["name"]) else resolved.get(spec["name"]))
            for spec in workflow["variables"]
        },
    }


def begin_run(
    workflow: dict[str, Any],
    *,
    inputs: dict[str, Any],
    simulation: bool = False,
) -> str:
    run_id = str(uuid.uuid4())
    safe_inputs = {
        spec["name"]: (
            "[fornecido]"
            if spec["secret"] and inputs.get(spec["name"]) not in (None, "")
            else operations.safe_payload(inputs.get(spec["name"]))
        )
        for spec in workflow["variables"]
    }
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO workflow_runs (
                id, workflow_id, workflow_version, state, simulation,
                input_json, result_json, operation_ids_json,
                started_at, finished_at
            ) VALUES (?, ?, ?, 'running', ?, ?, NULL, '[]', ?, NULL)
            """,
            (
                run_id,
                workflow["id"],
                workflow["version"],
                int(simulation),
                _json(safe_inputs),
                time.time(),
            ),
        )
        connection.commit()
    return run_id


def finish_run(
    run_id: str,
    *,
    state: str,
    result: dict[str, Any],
    operation_ids: list[str],
) -> dict[str, Any]:
    if state not in {"completed", "failed", "cancelled", "awaiting_approval"}:
        raise ValueError("Estado de execução inválido.")
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE workflow_runs
            SET state = ?, result_json = ?, operation_ids_json = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (
                state,
                _json(operations.safe_payload(result)),
                _json(operation_ids[:100]),
                time.time(),
                run_id,
            ),
        )
        connection.commit()
    item = get_run(run_id)
    if item is None:
        raise KeyError(run_id)
    return item


def get_run(run_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM workflow_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "workflow_id": row["workflow_id"],
        "workflow_version": int(row["workflow_version"]),
        "state": row["state"],
        "simulation": bool(row["simulation"]),
        "inputs": _loads(row["input_json"], {}),
        "result": _loads(row["result_json"], None),
        "operation_ids": _loads(row["operation_ids_json"], []),
        "started_at": float(row["started_at"]),
        "finished_at": row["finished_at"],
    }


def list_runs(workflow_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    if get_workflow(workflow_id) is None:
        raise KeyError(workflow_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT id FROM workflow_runs
            WHERE workflow_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (workflow_id, max(1, min(int(limit), 500))),
        ).fetchall()
    return [item for row in rows if (item := get_run(row["id"])) is not None]


def create_from_operations(
    *,
    name: str,
    operation_ids: list[str],
    description: str = "",
) -> dict[str, Any]:
    if not operation_ids or len(operation_ids) > _MAX_STEPS:
        raise ValueError("Selecione entre 1 e 30 operações.")
    steps: list[dict[str, Any]] = []
    for index, operation_id in enumerate(operation_ids):
        item = operations.get(str(operation_id))
        if item is None or item["state"] != "completed":
            raise ValueError("Somente operações concluídas podem virar workflow.")
        action = operations.action_for_workflow(str(operation_id))
        if action is None:
            raise ValueError(
                "O payload integral desta operação não está mais na memória. "
                "Repita a operação nesta sessão antes de transformá-la em workflow."
            )
        steps.append({
            "id": f"step-{index + 1}",
            "name": item["title"],
            "action": action,
            "continue_on_error": False,
        })
    return create_workflow(
        name=name,
        description=description,
        steps=steps,
        variables=[],
        enabled=True,
    )


_init_db()
