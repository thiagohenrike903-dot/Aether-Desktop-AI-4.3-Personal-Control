"""Persistent, honest operation tracking for Aether's Control Centre."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import sqlite3
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import safety_mode
from .config import settings
from .redaction import is_sensitive_field, redact_text, sanitize_url

logger = logging.getLogger("jarvis.operations")

OperationRunner = Callable[[dict[str, Any], bool], Awaitable[dict[str, Any]]]
UndoRunner = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]

STATES = {
    "pending",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
_TRANSITIONS = {
    "pending": {"running", "awaiting_approval", "failed", "cancelled"},
    "awaiting_approval": {"running", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"
_TASKS: dict[str, asyncio.Task[dict[str, Any]]] = {}
_ACTIONS: dict[str, dict[str, Any]] = {}
_COOPERATIVELY_CANCELLABLE_KINDS = {
    "web_search",
    "web_fetch",
    "weather",
    "weather_forecast",
    "email_list",
    "email_search",
    "calendar_list",
    "browser_navigate",
    "browser_screenshot",
    "browser_extract",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    title             TEXT NOT NULL,
    state             TEXT NOT NULL,
    progress          REAL NOT NULL DEFAULT 0,
    request_id        TEXT,
    permission_scope  TEXT NOT NULL,
    risk              TEXT NOT NULL,
    action_json       TEXT NOT NULL,
    affected_json     TEXT NOT NULL,
    result_json       TEXT,
    error             TEXT,
    can_cancel        INTEGER NOT NULL DEFAULT 1,
    can_retry         INTEGER NOT NULL DEFAULT 0,
    can_undo          INTEGER NOT NULL DEFAULT 0,
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL,
    started_at        REAL,
    finished_at       REAL,
    attempt           INTEGER NOT NULL DEFAULT 1,
    parent_id         TEXT
);
CREATE INDEX IF NOT EXISTS ix_operations_state_updated
ON operations(state, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_operations_request
ON operations(request_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS operation_events (
    id            TEXT PRIMARY KEY,
    operation_id  TEXT NOT NULL,
    type          TEXT NOT NULL,
    message       TEXT,
    data_json     TEXT NOT NULL,
    ts            REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_operation_events_operation
ON operation_events(operation_id, ts);
"""

def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        stale_rows = connection.execute(
            """
            SELECT id, state
            FROM operations
            WHERE state IN ('pending', 'awaiting_approval', 'running')
            """
        ).fetchall()
        now = time.time()
        for row in stale_rows:
            operation_id = str(row["id"])
            if operation_id in _ACTIONS:
                continue
            previous_state = str(row["state"])
            error = (
                "Operação interrompida pelo reinício do Aether. "
                "O payload integral não é persistido e a operação não pode ser retomada."
            )
            connection.execute(
                """
                UPDATE operations
                SET state = 'failed', error = ?, can_cancel = 0,
                    can_retry = 0, can_undo = 0, updated_at = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (error, now, now, operation_id),
            )
            connection.execute(
                """
                INSERT INTO operation_events
                    (id, operation_id, type, message, data_json, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    operation_id,
                    "restart_recovery",
                    error,
                    json.dumps(
                        {
                            "from": previous_state,
                            "to": "failed",
                            "recoverable": False,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )
        connection.commit()


_init_db()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[limite de profundidade]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key)[:160]
            normalized = key.lower().replace("-", "_")
            if is_sensitive_field(normalized):
                output[key] = "[redigido]"
                if isinstance(item, str):
                    output[f"{key}_length"] = len(item)
            elif normalized == "value":
                # Generic form values are frequently passwords or one-time
                # codes; the full action remains only in the in-memory cache.
                output[key] = "[redigido]"
                if isinstance(item, str):
                    output[f"{key}_length"] = len(item)
            elif normalized in {"body", "text", "content"}:
                # Message bodies, file contents and plaintext passed to crypto
                # are never required for a Control Centre audit row.
                output[key] = "[redigido]"
                if isinstance(item, str):
                    output[f"{key}_length"] = len(item)
            else:
                output[key] = _safe_payload(item, depth=depth + 1)
        return output
    if isinstance(value, list):
        return [_safe_payload(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        redacted = redact_text(value)
        return redacted[:4_000] + ("…" if len(redacted) > 4_000 else "")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value)[:1_000]


def safe_payload(value: Any) -> Any:
    """Redact and bound data before another control-plane table persists it."""
    return _safe_payload(value)


def affected_resources(action: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(action.get("type") or "action").lower()
    affected: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        fingerprint = _json(item)
        if fingerprint not in {_json(existing) for existing in affected}:
            affected.append(item)

    target = action.get("target")
    if kind == "email_send":
        recipient = str(action.get("to") or target or "").strip()
        if recipient:
            add({"type": "recipient", "name": recipient, "recipient": recipient})
    if kind.startswith("calendar_"):
        name = str(action.get("summary") or action.get("event_id") or "Calendário")
        add({"type": "calendar", "name": name})
    for key in ("source", "destination", "path", "file_path", "target_dir"):
        value = action.get(key)
        if isinstance(value, str) and value.strip():
            add({"type": "file", "name": Path(value).name or value, "path": value})
    if kind in {
        "file_operation",
        "organize_files",
        "clean_temp_files",
        "undo_organize_files",
        "pdf_extract_text",
        "pdf_extract_tables",
        "pdf_extract_images",
        "crypto_encrypt",
        "crypto_decrypt",
        "backup_create",
        "backup_restore",
        "git_status",
        "git_log",
        "git_diff",
        "git_add",
        "git_commit",
        "git_push",
        "git_pull",
        "git_merge",
        "git_branch_create",
        "git_branch_checkout",
        "workspace_set",
        "workspace_write",
        "workspace_create",
        "workspace_rename",
        "workspace_delete",
        "workspace_run",
    } and isinstance(target, str) and target.strip():
        add({"type": "file", "name": Path(target).name or target, "path": target})
    url = action.get("url")
    if not url and kind in {
        "open_url",
        "web_fetch",
        "browser_navigate",
        "browser_screenshot",
        "browser_extract",
        "browser_click",
        "browser_fill",
    }:
        url = target
    if isinstance(url, str) and url.strip():
        safe_url = sanitize_url(url)
        parsed = urlparse(safe_url)
        add({
            "type": "site",
            "name": parsed.hostname or safe_url,
            "url": safe_url,
        })
    if kind.startswith("plugin_"):
        name = str(target or action.get("name") or "Plugin")
        add({"type": "plugin", "name": name})
    if kind == "system_action":
        add({"type": "computer", "name": str(target or "Computador")})
    if not affected and target not in (None, ""):
        add({"type": "target", "name": str(target)[:300]})
    return affected


def _row_to_public(row: sqlite3.Row) -> dict[str, Any]:
    state = str(row["state"])
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "state": state,
        "progress": row["progress"],
        "request_id": row["request_id"],
        "permission_scope": row["permission_scope"],
        "risk": row["risk"],
        "action": _loads(row["action_json"], {}),
        "affected": _loads(row["affected_json"], []),
        "result": _loads(row["result_json"], None),
        "error": row["error"],
        "can_cancel": (
            state in {"pending", "awaiting_approval"}
            or (bool(row["can_cancel"]) and state == "running")
        ),
        "can_approve": (
            state == "awaiting_approval"
            and row["id"] in _ACTIONS
        ),
        "can_retry": (
            bool(row["can_retry"])
            and state in {"failed", "cancelled"}
            and row["id"] in _ACTIONS
        ),
        "can_undo": (
            bool(row["can_undo"])
            and state == "completed"
            and row["id"] in _ACTIONS
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "attempt": row["attempt"],
        "parent_id": row["parent_id"],
    }


def _event(
    operation_id: str,
    event_type: str,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "operation_id": operation_id,
        "type": event_type,
        "message": message,
        "data": _safe_payload(data or {}),
        "ts": time.time(),
    }
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO operation_events
                (id, operation_id, type, message, data_json, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                operation_id,
                event_type,
                redact_text(message)[:2_000],
                _json(item["data"]),
                item["ts"],
            ),
        )
        connection.commit()
    try:
        # Lazy import avoids a module cycle and keeps operation recording
        # available even if a damaged legacy ledger needs repair.
        from . import audit_integrity

        operation = get(operation_id)
        if operation is not None:
            audit_integrity.append_operation_event(
                operation,
                item,
                db_path=_DB_PATH,
            )
    except Exception as exc:  # pragma: no cover - defensive isolation
        logger.warning("Falha ao anexar evento à cadeia de auditoria: %s", exc)
    return item


def create(
    action: dict[str, Any],
    *,
    state: str = "pending",
    request_id: str | None = None,
    permission_scope: str | None = None,
    risk: str = "low",
    title: str | None = None,
    parent_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    if state not in STATES:
        raise ValueError("Estado de operação inválido.")
    kind = str(action.get("type") or "action").strip().lower()[:120] or "action"
    operation_id = str(uuid.uuid4())
    now = time.time()
    safe_action = _safe_payload(action)
    affected = affected_resources(action)
    operation_title = redact_text(str(
        title
        or action.get("title")
        or action.get("summary")
        or kind.replace("_", " ").title()
    ))[:240]
    can_undo = kind == "organize_files" and not bool(action.get("dry_run", True))
    runner_cancellable = kind in _COOPERATIVELY_CANCELLABLE_KINDS
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO operations (
                id, kind, title, state, progress, request_id,
                permission_scope, risk, action_json, affected_json,
                can_cancel, can_retry, can_undo, created_at, updated_at,
                attempt, parent_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_id,
                kind,
                operation_title,
                state,
                0.0,
                request_id,
                permission_scope or f"action:{kind}",
                risk,
                _json(safe_action),
                _json(affected),
                int(runner_cancellable),
                0,
                int(can_undo),
                now,
                now,
                max(1, int(attempt)),
                parent_id,
            ),
        )
        connection.commit()
    _ACTIONS[operation_id] = dict(action)
    _event(operation_id, "created", "Operação criada.", {"state": state})
    item = get(operation_id)
    assert item is not None
    return item


def get(operation_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM operations WHERE id = ?",
            (operation_id,),
        ).fetchone()
    return _row_to_public(row) if row else None


def action_for_workflow(operation_id: str) -> dict[str, Any] | None:
    """Return an in-memory action for explicit workflow conversion.

    Full action payloads are deliberately never read back from SQLite because
    audit rows are redacted. Consequently an operation can be converted only
    while its original payload is still held by the current Aether process.
    """
    item = get(operation_id)
    action = _ACTIONS.get(operation_id)
    if item is None or item["state"] != "completed" or action is None:
        return None
    return dict(action)


def list_operations(
    *,
    state: str | None = None,
    limit: int = 100,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    clauses: list[str] = []
    values: list[Any] = []
    if state:
        if state not in STATES:
            raise ValueError("Estado de operação inválido.")
        clauses.append("state = ?")
        values.append(state)
    if request_id:
        clauses.append("request_id = ?")
        values.append(request_id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(safe_limit)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM operations{where} ORDER BY updated_at DESC LIMIT ?",
            values,
        ).fetchall()
    return [_row_to_public(row) for row in rows]


def events(operation_id: str) -> list[dict[str, Any]]:
    if get(operation_id) is None:
        raise KeyError(operation_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, operation_id, type, message, data_json, ts
            FROM operation_events
            WHERE operation_id = ?
            ORDER BY ts, rowid
            """,
            (operation_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "operation_id": row["operation_id"],
            "type": row["type"],
            "message": row["message"],
            "data": _loads(row["data_json"], {}),
            "ts": row["ts"],
        }
        for row in rows
    ]


def export_audit(
    *,
    limit: int = 500,
    since: float | None = None,
    until: float | None = None,
) -> dict[str, Any]:
    """Export a bounded redacted snapshot of operations and their events."""
    safe_limit = max(1, min(int(limit), 1_000))
    if since is not None:
        since = float(since)
    if until is not None:
        until = float(until)
    if (
        (since is not None and not math.isfinite(since))
        or (until is not None and not math.isfinite(until))
    ):
        raise ValueError("O período da auditoria precisa usar timestamps finitos.")
    if since is not None and until is not None and since > until:
        raise ValueError("O início do período precisa ser anterior ao fim.")

    clauses: list[str] = []
    values: list[Any] = []
    if since is not None:
        clauses.append("created_at >= ?")
        values.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        values.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM operations
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            [*values, safe_limit + 1],
        ).fetchall()
        truncated = len(rows) > safe_limit
        rows = rows[:safe_limit]
        operation_ids = [str(row["id"]) for row in rows]
        event_rows: list[sqlite3.Row] = []
        if operation_ids:
            placeholders = ", ".join("?" for _ in operation_ids)
            event_rows = connection.execute(
                f"""
                SELECT id, operation_id, type, message, data_json, ts
                FROM operation_events
                WHERE operation_id IN ({placeholders})
                ORDER BY ts, rowid
                """,
                operation_ids,
            ).fetchall()

    events_by_operation: dict[str, list[dict[str, Any]]] = {
        operation_id: [] for operation_id in operation_ids
    }
    for row in event_rows:
        events_by_operation.setdefault(str(row["operation_id"]), []).append({
            "id": row["id"],
            "operation_id": row["operation_id"],
            "type": row["type"],
            "message": redact_text(row["message"] or "")[:2_000],
            "data": _safe_payload(_loads(row["data_json"], {})),
            "ts": row["ts"],
        })

    exported = [
        {
            **_row_to_public(row),
            "events": events_by_operation.get(str(row["id"]), []),
        }
        for row in rows
    ]
    canonical = json.dumps(
        exported,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    generated_at = time.time()
    return {
        "format": "aether-audit-v1",
        "generated_at": generated_at,
        "metadata": {
            "redacted": True,
            "contains_full_action_payloads": False,
            "operation_count": len(exported),
            "event_count": sum(len(item["events"]) for item in exported),
            "limit": safe_limit,
            "truncated": truncated,
            "filters": {"since": since, "until": until},
            "checksum": {
                "algorithm": "sha256",
                "scope": "operations",
                "value": hashlib.sha256(canonical).hexdigest(),
                "tamper_proof": False,
            },
        },
        "operations": exported,
    }


def transition(
    operation_id: str,
    state: str,
    *,
    progress: float | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if state not in STATES:
        raise ValueError("Estado de operação inválido.")
    current = get(operation_id)
    if current is None:
        raise KeyError(operation_id)
    if not force and state != current["state"] and state not in _TRANSITIONS[current["state"]]:
        raise ValueError(
            f"Transição inválida: {current['state']} -> {state}."
        )
    now = time.time()
    started_at = current["started_at"]
    finished_at = current["finished_at"]
    if state == "running" and started_at is None:
        started_at = now
    if state in TERMINAL_STATES:
        finished_at = now
    actual_progress = (
        max(0.0, min(1.0, float(progress)))
        if progress is not None
        else (1.0 if state == "completed" else current["progress"])
    )
    retryable = state in {"failed", "cancelled"} and operation_id in _ACTIONS
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE operations
            SET state = ?, progress = ?, result_json = ?, error = ?,
                can_cancel = ?, can_retry = ?, updated_at = ?,
                started_at = ?, finished_at = ?
            WHERE id = ?
            """,
            (
                state,
                actual_progress,
                _json(_safe_payload(result)) if result is not None else current["result"] and _json(current["result"]),
                redact_text(error)[:4_000] if error else None,
                int(
                    current["kind"] in _COOPERATIVELY_CANCELLABLE_KINDS
                    if state == "running"
                    else False
                ),
                int(retryable),
                now,
                started_at,
                finished_at,
                operation_id,
            ),
        )
        connection.commit()
    _event(
        operation_id,
        "state",
        f"Estado alterado para {state}.",
        {"from": current["state"], "to": state, "progress": actual_progress},
    )
    item = get(operation_id)
    assert item is not None
    return item


def set_progress(
    operation_id: str,
    progress: float,
    message: str = "",
) -> dict[str, Any]:
    current = get(operation_id)
    if current is None:
        raise KeyError(operation_id)
    if current["state"] != "running":
        raise ValueError("Somente operações em execução aceitam progresso.")
    value = max(0.0, min(0.99, float(progress)))
    with _LOCK, _connect() as connection:
        connection.execute(
            "UPDATE operations SET progress = ?, updated_at = ? WHERE id = ?",
            (value, time.time(), operation_id),
        )
        connection.commit()
    _event(operation_id, "progress", message, {"progress": value})
    item = get(operation_id)
    assert item is not None
    return item


def mark_awaiting_approval(operation_id: str) -> dict[str, Any]:
    return transition(operation_id, "awaiting_approval")


async def run_existing(
    operation_id: str,
    runner: OperationRunner,
    *,
    confirmed: bool = True,
) -> dict[str, Any]:
    operation, _raw_result = await run_existing_with_result(
        operation_id,
        runner,
        confirmed=confirmed,
    )
    return operation


async def run_existing_with_result(
    operation_id: str,
    runner: OperationRunner,
    *,
    confirmed: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run an operation and also return its in-memory, unredacted result.

    The public Control Centre representation remains redacted.  This companion
    is used only by compatibility endpoints that historically returned tool
    output directly (for example encrypted text) and therefore must not replace
    that output with the audit-log representation.
    """
    operation = get(operation_id)
    if operation is None:
        raise KeyError(operation_id)
    if operation["state"] not in {"pending", "awaiting_approval"}:
        raise ValueError("A operação não está aguardando execução.")
    action = _ACTIONS.get(operation_id)
    if action is None:
        raise ValueError(
            "Os dados integrais desta operação não permanecem após reiniciar; "
            "crie a ação novamente."
        )
    safety = safety_mode.preview(action, confirmed=confirmed)
    if safety["blocked"]:
        blocked = transition(
            operation_id,
            "failed",
            error=f"Operação bloqueada pelo modo seguro: {safety['reason']}",
        )
        _event(
            operation_id,
            "safety_mode_block",
            "O modo seguro impediu a execução.",
            {
                "mode": safety["mode"],
                "classification": safety["classification"],
                "action_kind": safety["action_kind"],
            },
        )
        return blocked, None
    if safety["requires_confirmation"]:
        if operation["state"] == "pending":
            operation = mark_awaiting_approval(operation_id)
        _event(
            operation_id,
            "safety_mode_approval",
            "O modo seguro exige aprovação antes da execução.",
            {
                "mode": safety["mode"],
                "classification": safety["classification"],
                "action_kind": safety["action_kind"],
            },
        )
        return get(operation_id) or operation, None
    transition(operation_id, "running", progress=0.05)

    async def invoke() -> dict[str, Any]:
        return await runner(action, confirmed)

    task = asyncio.create_task(invoke(), name=f"aether-operation-{operation_id}")
    _TASKS[operation_id] = task
    try:
        result = await asyncio.shield(task)
    except asyncio.CancelledError:
        current = get(operation_id)
        if current and current["can_cancel"]:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            if get(operation_id) and get(operation_id)["state"] == "running":
                transition(operation_id, "cancelled", error="Operação cancelada.")
        else:
            # The caller was cancelled but the underlying non-cooperative work
            # may still be running. Finalise it in the background and keep the
            # Control Centre honest about its state.
            async def finish_later() -> None:
                try:
                    late_result = await task
                    _finish(operation_id, late_result)
                except Exception as exc:
                    if get(operation_id) and get(operation_id)["state"] == "running":
                        transition(operation_id, "failed", error=str(exc))

            asyncio.create_task(
                finish_later(),
                name=f"aether-operation-finalize-{operation_id}",
            )
        return get(operation_id) or operation, None
    except Exception as exc:
        transition(operation_id, "failed", error=str(exc))
        return get(operation_id) or operation, None
    finally:
        _TASKS.pop(operation_id, None)

    return _finish(operation_id, result), result


def _finish(operation_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("pending_confirmation"):
        # A lower-level safety gate may still require approval.
        transition(operation_id, "awaiting_approval", result=result, force=True)
    elif result.get("ok"):
        transition(operation_id, "completed", progress=1.0, result=result)
    elif result.get("cancelled"):
        transition(operation_id, "cancelled", result=result)
    else:
        transition(
            operation_id,
            "failed",
            result=result,
            error=str(result.get("error") or "A operação falhou."),
        )
    current = get(operation_id)
    if current is None:
        raise KeyError(operation_id)
    return current


async def cancel(operation_id: str) -> dict[str, Any]:
    operation = get(operation_id)
    if operation is None:
        raise KeyError(operation_id)
    if operation["state"] in TERMINAL_STATES:
        return operation
    if operation["state"] == "running" and not operation["can_cancel"]:
        raise ValueError(
            "Esta ferramenta não oferece cancelamento imediato seguro enquanto executa."
        )
    task = _TASKS.get(operation_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        await asyncio.sleep(0)
    current = get(operation_id)
    if current and current["state"] in {"pending", "awaiting_approval"}:
        transition(operation_id, "cancelled", error="Operação cancelada pelo usuário.")
    elif current and current["state"] == "running" and current["can_cancel"]:
        transition(operation_id, "cancelled", error="Operação cancelada pelo usuário.")
    return get(operation_id) or operation


async def cancel_for_request(request_id: str) -> list[str]:
    items = list_operations(request_id=request_id, limit=100)
    cancelled: list[str] = []
    for item in items:
        if item["state"] not in TERMINAL_STATES:
            try:
                await cancel(item["id"])
            except ValueError:
                continue
            cancelled.append(item["id"])
    return cancelled


async def retry(
    operation_id: str,
    runner: OperationRunner,
) -> dict[str, Any]:
    from . import permissions

    previous = get(operation_id)
    if previous is None:
        raise KeyError(operation_id)
    if previous["state"] not in {"failed", "cancelled"}:
        raise ValueError("Somente operações falhas ou canceladas podem ser repetidas.")
    action = _ACTIONS.get(operation_id)
    if action is None:
        raise ValueError("Esta operação não pode ser repetida após reiniciar o Aether.")
    repeated = create(
        action,
        request_id=previous["request_id"],
        permission_scope=previous["permission_scope"],
        risk=previous["risk"],
        title=previous["title"],
        parent_id=operation_id,
        attempt=int(previous["attempt"]) + 1,
    )
    permission = permissions.decision(
        repeated["permission_scope"],
        risk=repeated["risk"],
        confirmed=False,
        project_id=str(action.get("project_id") or "") or None,
    )
    if permission == "block":
        return transition(
            repeated["id"],
            "failed",
            error="A operação foi bloqueada pela política de permissões.",
        )
    if permission == "ask":
        return mark_awaiting_approval(repeated["id"])
    return await run_existing(repeated["id"], runner, confirmed=True)


async def undo(
    operation_id: str,
    undo_runner: UndoRunner,
    *,
    confirmed: bool = False,
) -> dict[str, Any]:
    from . import permissions

    operation = get(operation_id)
    if operation is None:
        raise KeyError(operation_id)
    if operation["state"] != "completed" or not operation["can_undo"]:
        raise ValueError("Esta operação não possui um desfazer seguro.")
    action = _ACTIONS.get(operation_id)
    if action is None:
        raise ValueError("Esta operação não pode ser desfeita após reiniciar o Aether.")
    safety = safety_mode.preview(
        {
            "type": "undo_organize_files",
            "project_id": action.get("project_id"),
        },
        confirmed=confirmed,
        project_id=str(action.get("project_id") or "") or None,
    )
    if safety["blocked"]:
        _event(
            operation_id,
            "undo_safety_block",
            "O modo seguro impediu o desfazer.",
            {
                "mode": safety["mode"],
                "classification": safety["classification"],
            },
        )
        return {
            "ok": False,
            "blocked": True,
            "error": f"Desfazer bloqueado pelo modo seguro: {safety['reason']}",
            "operation": get(operation_id),
            "safety": safety,
        }
    if safety["requires_confirmation"]:
        _event(
            operation_id,
            "undo_safety_approval",
            "O modo seguro exige aprovação para desfazer.",
            {
                "mode": safety["mode"],
                "classification": safety["classification"],
            },
        )
        return {
            "ok": False,
            "pending_confirmation": True,
            "error": "O modo confirmar tudo exige aprovação para desfazer.",
            "operation": get(operation_id),
            "safety": safety,
        }
    permission = permissions.decision(
        "action:undo_organize_files",
        risk=str(operation.get("risk") or "high"),
        confirmed=confirmed,
        project_id=str(action.get("project_id") or "") or None,
    )
    if permission == "block":
        _event(
            operation_id,
            "undo_permission_block",
            "A política de permissões impediu o desfazer.",
        )
        return {
            "ok": False,
            "blocked": True,
            "error": "A política de permissões bloqueia esta ação de desfazer.",
            "operation": get(operation_id),
            "safety": safety,
        }
    if permission == "ask":
        _event(
            operation_id,
            "undo_permission_approval",
            "A política de permissões exige aprovação para desfazer.",
        )
        return {
            "ok": False,
            "pending_confirmation": True,
            "error": "Esta ação de desfazer precisa de aprovação explícita.",
            "operation": get(operation_id),
            "safety": safety,
        }
    result = await undo_runner(action, operation.get("result") or {})
    if result.get("ok"):
        with _LOCK, _connect() as connection:
            connection.execute(
                """
                UPDATE operations
                SET can_undo = 0, updated_at = ?
                WHERE id = ?
                """,
                (time.time(), operation_id),
            )
            connection.commit()
        _event(operation_id, "undo", "Operação desfeita.", result)
    else:
        _event(
            operation_id,
            "undo_failed",
            str(result.get("error") or "Não foi possível desfazer."),
            result,
        )
    return {"ok": bool(result.get("ok")), "operation": get(operation_id), "result": result}
