"""Action permission policies for the Aether control centre.

Persistent policies intentionally support only ``ask`` and ``block``.
``session_allow`` lives in memory and is discarded when the core process
stops, matching the promise made by the UI.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import safety_mode
from .config import settings

VALID_MODES = {"ask", "session_allow", "block"}

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"
_SESSION_POLICIES: dict[str, float] = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS permission_policies (
    scope       TEXT PRIMARY KEY,
    mode        TEXT NOT NULL,
    updated_at  REAL NOT NULL
);
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


def normalize_scope(scope: str) -> str:
    value = str(scope or "").strip().lower()
    if not value or len(value) > 180:
        raise ValueError("Escopo de permissão inválido.")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789:_-.*" for char in value):
        raise ValueError("Escopo de permissão inválido.")
    return value


def set_policy(scope: str, mode: str) -> dict[str, Any]:
    scope = normalize_scope(scope)
    mode = str(mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError("Modo inválido. Use ask, session_allow ou block.")
    now = time.time()
    with _LOCK:
        if mode == "session_allow":
            _SESSION_POLICIES[scope] = now
            with _connect() as connection:
                connection.execute(
                    "DELETE FROM permission_policies WHERE scope = ?",
                    (scope,),
                )
                connection.commit()
        else:
            _SESSION_POLICIES.pop(scope, None)
            with _connect() as connection:
                connection.execute(
                    """
                    INSERT INTO permission_policies (scope, mode, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(scope)
                    DO UPDATE SET mode = excluded.mode, updated_at = excluded.updated_at
                    """,
                    (scope, mode, now),
                )
                connection.commit()
    return {
        "scope": scope,
        "mode": mode,
        "session_only": mode == "session_allow",
        "updated_at": now,
    }


def delete_policy(scope: str) -> bool:
    scope = normalize_scope(scope)
    with _LOCK:
        removed_session = _SESSION_POLICIES.pop(scope, None) is not None
        with _connect() as connection:
            result = connection.execute(
                "DELETE FROM permission_policies WHERE scope = ?",
                (scope,),
            )
            connection.commit()
    return removed_session or result.rowcount > 0


def reset_session() -> int:
    with _LOCK:
        count = len(_SESSION_POLICIES)
        _SESSION_POLICIES.clear()
    return count


def list_policies() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT scope, mode, updated_at FROM permission_policies ORDER BY scope"
        ).fetchall()
        persisted = [
            {
                "scope": row["scope"],
                "mode": row["mode"],
                "session_only": False,
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        session = [
            {
                "scope": scope,
                "mode": "session_allow",
                "session_only": True,
                "updated_at": updated_at,
            }
            for scope, updated_at in sorted(_SESSION_POLICIES.items())
        ]
    by_scope = {item["scope"]: item for item in persisted}
    by_scope.update({item["scope"]: item for item in session})
    return list(by_scope.values())


def _candidate_scopes(scope: str) -> list[str]:
    """Return exact-to-broad scopes, including the global wildcard."""
    parts = scope.split(":")
    candidates = [scope]
    if len(parts) > 1:
        candidates.append(f"{parts[0]}:*")
    candidates.append("*")
    return list(dict.fromkeys(candidates))


def get_mode(scope: str, *, default: str = "ask") -> str:
    scope = normalize_scope(scope)
    if default not in VALID_MODES:
        raise ValueError("Modo padrão inválido.")
    candidates = _candidate_scopes(scope)
    with _LOCK:
        with _connect() as connection:
            for candidate in candidates:
                # Specificity wins across both storage classes. A broad
                # session allow must never bypass an exact persistent block.
                if candidate in _SESSION_POLICIES:
                    return "session_allow"
                row = connection.execute(
                    "SELECT mode FROM permission_policies WHERE scope = ?",
                    (candidate,),
                ).fetchone()
                if row:
                    return str(row["mode"])
    return default


def decision(
    scope: str,
    *,
    risk: str,
    confirmed: bool = False,
    project_id: str | None = None,
) -> str:
    """Return ``allow``, ``ask`` or ``block`` for an operation.

    Low-risk actions continue to run by default for 4.0 compatibility. An
    explicit ``ask`` policy still takes effect when it exists.
    """
    scope = normalize_scope(scope)
    candidates = _candidate_scopes(scope)
    with _LOCK:
        explicitly_configured = any(
            candidate in _SESSION_POLICIES for candidate in candidates
        )
        if not explicitly_configured:
            with _connect() as connection:
                explicitly_configured = any(
                    connection.execute(
                        "SELECT 1 FROM permission_policies WHERE scope = ?",
                        (candidate,),
                    ).fetchone()
                    is not None
                    for candidate in candidates
                )
    policy_mode = get_mode(scope)
    if policy_mode == "block":
        permission_result = "block"
    elif confirmed or policy_mode == "session_allow":
        permission_result = "allow"
    elif risk == "low" and not explicitly_configured:
        permission_result = "allow"
    else:
        permission_result = "ask"

    # The global safety mode is a ceiling, never a bypass. In particular,
    # session_allow cannot override read_only and an explicit block cannot be
    # overridden by confirm_all approval.
    global_result = safety_mode.decision(
        scope,
        confirmed=confirmed,
        project_id=project_id,
    )
    if "block" in {permission_result, global_result}:
        return "block"
    if "ask" in {permission_result, global_result}:
        return "ask"
    return "allow"
