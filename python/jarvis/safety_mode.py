"""Global, fail-closed safety mode for Aether actions.

The per-scope permission engine answers whether a user policy allows an
action.  This module adds a product-wide ceiling:

``normal``
    Preserve the existing permission behaviour.
``confirm_all``
    Every *known* action needs an explicit confirmation.
``read_only``
    Only actions on the explicit read allowlist may proceed.

Action capabilities intentionally live in one registry.  A new or malformed
action is classified as ``unknown`` and is blocked by every restrictive mode
until it is reviewed and added here.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .config import settings

VALID_MODES = frozenset({"normal", "confirm_all", "read_only"})
SUSPENDABLE_COMPONENTS = frozenset({"automations", "plugins"})
READ_CLASS = "read"
MUTATING_CLASS = "mutating"
UNKNOWN_CLASS = "unknown"

# This registry mirrors the structured action contract implemented by the
# executor.  Keep it explicit: prefix matching would let a newly introduced
# action inherit privileges without a security review.
_ACTION_CAPABILITIES = {
    # Local/system inspection.
    "list_processes": READ_CLASS,
    "system_snapshot": READ_CLASS,
    "list_installed_apps": READ_CLASS,
    "list_directory": READ_CLASS,
    # Public information retrieval.
    "web_search": READ_CLASS,
    "web_fetch": READ_CLASS,
    "weather": READ_CLASS,
    "weather_forecast": READ_CLASS,
    # Repository inspection.
    "git_status": READ_CLASS,
    "git_log": READ_CLASS,
    "git_diff": READ_CLASS,
    "git_branch": READ_CLASS,
    # Connected-account inspection.
    "email_list": READ_CLASS,
    "email_search": READ_CLASS,
    "calendar_list": READ_CLASS,
    # Local document inspection.
    "pdf_extract_text": READ_CLASS,
    "pdf_extract_tables": READ_CLASS,
    "pdf_extract_images": READ_CLASS,
    "backup_list": READ_CLASS,
    "plugin_list": READ_CLASS,
    # Browser reads are classified explicitly even though network browser
    # automation remains disabled in this release.
    "browser_screenshot": READ_CLASS,
    "browser_extract": READ_CLASS,
    # Product/control-plane inspection.
    "project_list": READ_CLASS,
    "project_get": READ_CLASS,
    "document_list": READ_CLASS,
    "document_search": READ_CLASS,
    "memory_list": READ_CLASS,
    "skill_list": READ_CLASS,
    "automation_list": READ_CLASS,
    "automation_history": READ_CLASS,
    "model_profile_list": READ_CLASS,
    "permission_list": READ_CLASS,
    "audit_search": READ_CLASS,
    "audit_verify": READ_CLASS,
    "privacy_map": READ_CLASS,
    "agent_status": READ_CLASS,
    "experience_profile_list": READ_CLASS,
    "connection_list": READ_CLASS,
    "connection_test": READ_CLASS,
    "response_verify": READ_CLASS,
    "model_lab_list": READ_CLASS,
    "workflow_list": READ_CLASS,
    "workflow_simulate": READ_CLASS,
    "system_health_check": READ_CLASS,
    "simulation_list": READ_CLASS,
    "evaluation_list": READ_CLASS,
    "evaluation_release_gate": READ_CLASS,
    # Desktop and system state changes.
    "open_app": MUTATING_CLASS,
    "open_path": MUTATING_CLASS,
    "open_url": MUTATING_CLASS,
    "kill_app": MUTATING_CLASS,
    "system_action": MUTATING_CLASS,
    "set_volume": MUTATING_CLASS,
    "set_volume_delta": MUTATING_CLASS,
    "set_brightness": MUTATING_CLASS,
    "media_command": MUTATING_CLASS,
    "minimize_active_window": MUTATING_CLASS,
    "search_web": MUTATING_CLASS,
    "capture_and_analyze": MUTATING_CLASS,
    # File/workspace state changes. Dry-run variants stay conservative because
    # permissions currently pass only ``action:<kind>`` to the global gate.
    "organize_files": MUTATING_CLASS,
    "clean_temp_files": MUTATING_CLASS,
    "undo_organize_files": MUTATING_CLASS,
    "file_operation": MUTATING_CLASS,
    "workspace_set": MUTATING_CLASS,
    "workspace_write": MUTATING_CLASS,
    "workspace_create": MUTATING_CLASS,
    "workspace_rename": MUTATING_CLASS,
    "workspace_delete": MUTATING_CLASS,
    "workspace_run": MUTATING_CLASS,
    # Repository, communication and calendar changes.
    "git_add": MUTATING_CLASS,
    "git_commit": MUTATING_CLASS,
    "git_push": MUTATING_CLASS,
    "git_pull": MUTATING_CLASS,
    "git_branch_create": MUTATING_CLASS,
    "git_branch_checkout": MUTATING_CLASS,
    "git_merge": MUTATING_CLASS,
    "email_send": MUTATING_CLASS,
    "calendar_create": MUTATING_CLASS,
    "calendar_delete": MUTATING_CLASS,
    # Local security/archive changes.
    "crypto_encrypt": MUTATING_CLASS,
    "crypto_decrypt": MUTATING_CLASS,
    "crypto_encrypt_text": MUTATING_CLASS,
    "crypto_decrypt_text": MUTATING_CLASS,
    "backup_create": MUTATING_CLASS,
    "backup_restore": MUTATING_CLASS,
    # Plugins and interactive browser actions.
    "plugin_load": MUTATING_CLASS,
    "plugin_unload": MUTATING_CLASS,
    "plugin_reload": MUTATING_CLASS,
    "plugin_install": MUTATING_CLASS,
    "plugin_run": MUTATING_CLASS,
    "browser_navigate": MUTATING_CLASS,
    "browser_click": MUTATING_CLASS,
    "browser_fill": MUTATING_CLASS,
    # Product/control-plane changes.  These do not all pass through the legacy
    # executor yet, but restrictive modes still need an explicit answer when
    # the UI exposes their CRUD endpoints.
    "project_create": MUTATING_CLASS,
    "project_update": MUTATING_CLASS,
    "project_archive": MUTATING_CLASS,
    "project_delete": MUTATING_CLASS,
    "document_import": MUTATING_CLASS,
    "document_delete": MUTATING_CLASS,
    "document_reindex": MUTATING_CLASS,
    "memory_create": MUTATING_CLASS,
    "memory_update": MUTATING_CLASS,
    "memory_delete": MUTATING_CLASS,
    "skill_create": MUTATING_CLASS,
    "skill_update": MUTATING_CLASS,
    "skill_delete": MUTATING_CLASS,
    "skill_restore": MUTATING_CLASS,
    "skill_import": MUTATING_CLASS,
    "skill_duplicate": MUTATING_CLASS,
    "automation_create": MUTATING_CLASS,
    "automation_update": MUTATING_CLASS,
    "automation_delete": MUTATING_CLASS,
    "automation_enable": MUTATING_CLASS,
    "automation_run": MUTATING_CLASS,
    "model_profile_update": MUTATING_CLASS,
    "model_profile_activate": MUTATING_CLASS,
    "model_profile_reset_usage": MUTATING_CLASS,
    "permission_update": MUTATING_CLASS,
    "permission_delete": MUTATING_CLASS,
    "permission_reset": MUTATING_CLASS,
    "safety_mode_update": MUTATING_CLASS,
    "safety_project_policy_update": MUTATING_CLASS,
    "component_suspend": MUTATING_CLASS,
    "component_resume": MUTATING_CLASS,
    "privacy_mode_update": MUTATING_CLASS,
    "conversation_create": MUTATING_CLASS,
    "conversation_update": MUTATING_CLASS,
    "conversation_delete": MUTATING_CLASS,
    "message_create": MUTATING_CLASS,
    "message_update": MUTATING_CLASS,
    "message_delete": MUTATING_CLASS,
    "workflow_create": MUTATING_CLASS,
    "workflow_update": MUTATING_CLASS,
    "workflow_delete": MUTATING_CLASS,
    "workflow_restore": MUTATING_CLASS,
    "agent_manifest_update": MUTATING_CLASS,
    "experience_profile_create": MUTATING_CLASS,
    "experience_profile_update": MUTATING_CLASS,
    "experience_profile_delete": MUTATING_CLASS,
    "experience_profile_activate": MUTATING_CLASS,
    "model_lab_preset_create": MUTATING_CLASS,
    "model_lab_compare": MUTATING_CLASS,
    "model_lab_select_winner": MUTATING_CLASS,
    "model_lab_create_profile": MUTATING_CLASS,
    "workflow_run": MUTATING_CLASS,
    "system_health_repair": MUTATING_CLASS,
    "simulation_create": MUTATING_CLASS,
    "simulation_approve": MUTATING_CLASS,
    "simulation_convert": MUTATING_CLASS,
    "evaluation_case_create": MUTATING_CLASS,
    "evaluation_preset_create": MUTATING_CLASS,
    "evaluation_run": MUTATING_CLASS,
}

ACTION_CAPABILITIES = MappingProxyType(_ACTION_CAPABILITIES)
READ_ONLY_ACTIONS = frozenset(
    kind for kind, capability in _ACTION_CAPABILITIES.items()
    if capability == READ_CLASS
)
MUTATING_ACTIONS = frozenset(
    kind for kind, capability in _ACTION_CAPABILITIES.items()
    if capability == MUTATING_CLASS
)
KNOWN_ACTIONS = frozenset(_ACTION_CAPABILITIES)

_ACTION_KIND_PATTERN = re.compile(r"[a-z0-9][a-z0-9_]{0,119}")
_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS safety_mode (
    singleton   INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode        TEXT NOT NULL CHECK (mode IN ('normal', 'confirm_all', 'read_only')),
    updated_at  REAL NOT NULL
);
INSERT OR IGNORE INTO safety_mode (singleton, mode, updated_at)
VALUES (1, 'normal', 0);
CREATE TABLE IF NOT EXISTS project_safety_policies (
    project_id   TEXT PRIMARY KEY,
    mode         TEXT NOT NULL CHECK (mode IN ('normal', 'confirm_all', 'read_only')),
    updated_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_suspensions (
    component    TEXT PRIMARY KEY CHECK (component IN ('automations', 'plugins')),
    suspended    INTEGER NOT NULL DEFAULT 0,
    reason       TEXT NOT NULL DEFAULT '',
    updated_at   REAL NOT NULL
);
INSERT OR IGNORE INTO runtime_suspensions
    (component, suspended, reason, updated_at)
VALUES
    ('automations', 0, '', 0),
    ('plugins', 0, '', 0);
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


def normalize_mode(mode: str) -> str:
    value = str(mode or "").strip().lower()
    if value not in VALID_MODES:
        raise ValueError(
            "Modo seguro inválido. Use normal, confirm_all ou read_only."
        )
    return value


def get_state() -> dict[str, Any]:
    """Return the persisted global mode.

    The CHECK constraint protects normal writes.  If an older or externally
    modified database nevertheless contains an invalid value, restrictive
    ``read_only`` is used rather than silently falling back to ``normal``.
    """
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT mode, updated_at FROM safety_mode WHERE singleton = 1"
        ).fetchone()
    if row is None:
        _init_db()
        return {"mode": "normal", "updated_at": 0.0, "integrity_fallback": False}
    raw_mode = str(row["mode"] or "").strip().lower()
    integrity_fallback = raw_mode not in VALID_MODES
    return {
        "mode": "read_only" if integrity_fallback else raw_mode,
        "updated_at": float(row["updated_at"]),
        "integrity_fallback": integrity_fallback,
    }


def get_mode() -> str:
    return str(get_state()["mode"])


def set_mode(mode: str) -> dict[str, Any]:
    value = normalize_mode(mode)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO safety_mode (singleton, mode, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(singleton)
            DO UPDATE SET mode = excluded.mode, updated_at = excluded.updated_at
            """,
            (value, now),
        )
        connection.commit()
    return {
        "mode": value,
        "updated_at": now,
        "integrity_fallback": False,
    }


def _normalize_project_id(project_id: str) -> str:
    value = str(project_id or "").strip()
    if not value or len(value) > 240:
        raise ValueError("Identificador de projeto inválido.")
    return value


def set_project_policy(project_id: str, mode: str) -> dict[str, Any]:
    """Persist the safety ceiling for one project."""
    identifier = _normalize_project_id(project_id)
    value = normalize_mode(mode)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO project_safety_policies (project_id, mode, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id)
            DO UPDATE SET mode = excluded.mode, updated_at = excluded.updated_at
            """,
            (identifier, value, now),
        )
        connection.commit()
    return {"project_id": identifier, "mode": value, "updated_at": now}


def get_project_policy(project_id: str) -> dict[str, Any] | None:
    identifier = _normalize_project_id(project_id)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT project_id, mode, updated_at
            FROM project_safety_policies
            WHERE project_id = ?
            """,
            (identifier,),
        ).fetchone()
    if row is None:
        return None
    raw_mode = str(row["mode"] or "").strip().lower()
    fallback = raw_mode not in VALID_MODES
    return {
        "project_id": str(row["project_id"]),
        "mode": "read_only" if fallback else raw_mode,
        "updated_at": float(row["updated_at"]),
        "integrity_fallback": fallback,
    }


def list_project_policies() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT project_id FROM project_safety_policies
            ORDER BY updated_at DESC, project_id
            """
        ).fetchall()
    return [
        policy
        for row in rows
        if (policy := get_project_policy(str(row["project_id"]))) is not None
    ]


def delete_project_policy(project_id: str) -> bool:
    identifier = _normalize_project_id(project_id)
    with _LOCK, _connect() as connection:
        result = connection.execute(
            "DELETE FROM project_safety_policies WHERE project_id = ?",
            (identifier,),
        )
        connection.commit()
    return result.rowcount > 0


def _component(value: str) -> str:
    component = str(value or "").strip().lower()
    if component not in SUSPENDABLE_COMPONENTS:
        raise ValueError("Componente inválido. Use automations ou plugins.")
    return component


def get_suspension(component: str) -> dict[str, Any]:
    value = _component(component)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT component, suspended, reason, updated_at
            FROM runtime_suspensions
            WHERE component = ?
            """,
            (value,),
        ).fetchone()
    if row is None:
        _init_db()
        return {
            "component": value,
            "suspended": False,
            "reason": "",
            "updated_at": 0.0,
        }
    return {
        "component": str(row["component"]),
        "suspended": bool(row["suspended"]),
        "reason": str(row["reason"] or ""),
        "updated_at": float(row["updated_at"]),
    }


def list_suspensions() -> dict[str, dict[str, Any]]:
    return {
        component: get_suspension(component)
        for component in sorted(SUSPENDABLE_COMPONENTS)
    }


def is_suspended(component: str) -> bool:
    return bool(get_suspension(component)["suspended"])


def suspend(component: str, reason: str = "") -> dict[str, Any]:
    value = _component(component)
    now = time.time()
    clean_reason = str(reason or "Suspenso pelo usuário.").strip()[:500]
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO runtime_suspensions
                (component, suspended, reason, updated_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT(component)
            DO UPDATE SET suspended = 1, reason = excluded.reason,
                          updated_at = excluded.updated_at
            """,
            (value, clean_reason, now),
        )
        connection.commit()
    return {
        "component": value,
        "suspended": True,
        "reason": clean_reason,
        "updated_at": now,
    }


def resume(component: str) -> dict[str, Any]:
    value = _component(component)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO runtime_suspensions
                (component, suspended, reason, updated_at)
            VALUES (?, 0, '', ?)
            ON CONFLICT(component)
            DO UPDATE SET suspended = 0, reason = '',
                          updated_at = excluded.updated_at
            """,
            (value, now),
        )
        connection.commit()
    return {
        "component": value,
        "suspended": False,
        "reason": "",
        "updated_at": now,
    }


def suspend_all(reason: str = "") -> dict[str, Any]:
    """Persist the emergency stop for every suspendable component.

    The plugin layer additionally unloads registered handlers.  Python code
    already executing in a thread cannot be force-killed safely; callers get
    that limitation explicitly instead of a false success claim.
    """
    states = {
        component: suspend(component, reason)
        for component in sorted(SUSPENDABLE_COMPONENTS)
    }
    return {
        "suspended": True,
        "components": states,
        "in_flight_terminated": False,
        "note": (
            "Novas automações e execuções de plugins foram bloqueadas. "
            "Código de plugin que já estava executando no processo não pode "
            "ser encerrado à força com segurança."
        ),
    }


def resume_all() -> dict[str, Any]:
    states = {
        component: resume(component)
        for component in sorted(SUSPENDABLE_COMPONENTS)
    }
    return {"suspended": False, "components": states}


def action_kind(action_or_scope: Mapping[str, Any] | str | None) -> str:
    """Extract a normalized action kind from an action or ``action:<kind>``."""
    if isinstance(action_or_scope, Mapping):
        raw = action_or_scope.get("type")
    else:
        raw = action_or_scope
    value = str(raw or "").strip().lower()
    if value.startswith("action:"):
        value = value[len("action:"):]
    if not _ACTION_KIND_PATTERN.fullmatch(value):
        return ""
    return value


def classify_action(action_or_scope: Mapping[str, Any] | str | None) -> str:
    """Return ``read``, ``mutating`` or fail-closed ``unknown``."""
    return ACTION_CAPABILITIES.get(action_kind(action_or_scope), UNKNOWN_CLASS)


def _decision_for(
    mode: str,
    classification: str,
    *,
    confirmed: bool,
) -> str:
    if mode == "normal":
        return "allow"
    if classification == UNKNOWN_CLASS:
        return "block"
    if mode == "read_only":
        return "allow" if classification == READ_CLASS else "block"
    # confirm_all
    return "allow" if confirmed else "ask"


_MODE_SEVERITY = {
    "normal": 0,
    "confirm_all": 1,
    "read_only": 2,
}


def _project_from_action(
    action_or_scope: Mapping[str, Any] | str | None,
    project_id: str | None,
) -> str | None:
    if project_id:
        return str(project_id).strip() or None
    if isinstance(action_or_scope, Mapping):
        value = action_or_scope.get("project_id")
        return str(value).strip() or None if value is not None else None
    return None


def effective_mode(
    action_or_scope: Mapping[str, Any] | str | None = None,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return the strictest global/project mode applicable to an action."""
    global_state = get_state()
    identifier = _project_from_action(action_or_scope, project_id)
    project_policy = get_project_policy(identifier) if identifier else None
    modes = [str(global_state["mode"])]
    if project_policy:
        modes.append(str(project_policy["mode"]))
    value = max(modes, key=lambda item: _MODE_SEVERITY[item])
    return {
        "mode": value,
        "global_mode": str(global_state["mode"]),
        "project_id": identifier,
        "project_mode": (
            str(project_policy["mode"]) if project_policy is not None else None
        ),
        "project_policy": project_policy,
        "integrity_fallback": bool(global_state["integrity_fallback"])
        or bool((project_policy or {}).get("integrity_fallback")),
    }


def decision(
    action_or_scope: Mapping[str, Any] | str | None,
    *,
    confirmed: bool = False,
    project_id: str | None = None,
) -> str:
    """Return the decision imposed by the global mode only.

    Per-scope policies are composed with this decision by ``permissions``.
    ``normal`` deliberately returns ``allow`` even for an unknown action to
    preserve the legacy policy/executor contract. Restrictive modes are
    fail-closed.
    """
    mode = str(
        effective_mode(action_or_scope, project_id=project_id)["mode"]
    )
    classification = classify_action(action_or_scope)
    return _decision_for(mode, classification, confirmed=confirmed)


def preview(
    action_or_scope: Mapping[str, Any] | str | None,
    *,
    confirmed: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Explain the global decision without executing or changing anything."""
    global_state = get_state()
    effective = effective_mode(action_or_scope, project_id=project_id)
    state = {
        **global_state,
        "global_mode": effective["global_mode"],
        "effective_mode": effective["mode"],
        "project_id": effective["project_id"],
        "project_mode": effective["project_mode"],
        "project_policy": effective["project_policy"],
        "integrity_fallback": effective["integrity_fallback"],
    }
    kind = action_kind(action_or_scope)
    classification = classify_action(action_or_scope)
    result = _decision_for(
        str(effective["mode"]),
        classification,
        confirmed=confirmed,
    )
    if effective["mode"] == "normal":
        reason = (
            "Modo normal: a política específica de permissões ainda se aplica."
        )
    elif classification == UNKNOWN_CLASS:
        reason = (
            "Tipo de ação desconhecido; modos restritivos bloqueiam por padrão."
        )
    elif effective["mode"] == "read_only" and classification != READ_CLASS:
        reason = "O modo somente leitura bloqueia ações que alteram estado."
    elif result == "ask":
        reason = "O modo confirmar tudo exige aprovação explícita."
    else:
        reason = "A ação é compatível com o modo seguro atual."
    return {
        **state,
        "action_kind": kind or None,
        "classification": classification,
        "known": classification != UNKNOWN_CLASS,
        "decision": result,
        "allowed": result == "allow",
        "requires_confirmation": result == "ask",
        "blocked": result == "block",
        "reason": reason,
    }
