"""Personalised home and reading profiles for Aether.

The profile is deliberately local and contains presentation choices only.  It
never stores message bodies, document contents, credentials, or executable
automation payloads.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

_MODULES = {
    "shortcuts",
    "pinned_projects",
    "recent_projects",
    "pinned_automations",
    "recent_conversations",
    "system_health",
    "privacy_summary",
}
_SHORTCUTS = {
    "new_chat",
    "research",
    "new_project",
    "import_document",
    "new_workflow",
    "model_lab",
    "control_center",
    "system_health",
}
_WIDTHS = {"narrow", "balanced", "wide", "full"}
_SPACINGS = {"compact", "comfortable", "airy"}
_CONTRASTS = {"standard", "high"}
_FONTS = {"system", "accessible", "serif", "dyslexic"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experience_profiles (
    id                         TEXT PRIMARY KEY,
    name                       TEXT NOT NULL,
    kind                       TEXT NOT NULL,
    home_json                  TEXT NOT NULL,
    reading_json               TEXT NOT NULL,
    active                     INTEGER NOT NULL DEFAULT 0,
    protected                  INTEGER NOT NULL DEFAULT 0,
    revision                   INTEGER NOT NULL DEFAULT 1,
    created_at                 REAL NOT NULL,
    updated_at                 REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_experience_active
ON experience_profiles(active)
WHERE active = 1;
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _default_home(kind: str) -> dict[str, Any]:
    shortcuts = {
        "work": ["new_chat", "new_project", "research", "control_center"],
        "study": ["new_chat", "research", "import_document", "model_lab"],
        "personal": ["new_chat", "research", "new_workflow", "system_health"],
    }[kind]
    modules = {
        "work": [
            "shortcuts",
            "pinned_projects",
            "pinned_automations",
            "recent_conversations",
            "system_health",
        ],
        "study": [
            "shortcuts",
            "pinned_projects",
            "recent_projects",
            "recent_conversations",
            "privacy_summary",
        ],
        "personal": [
            "shortcuts",
            "recent_projects",
            "pinned_automations",
            "system_health",
            "privacy_summary",
        ],
    }[kind]
    return {
        "module_order": modules,
        "hidden_modules": [],
        "shortcut_ids": shortcuts,
        "pinned_project_ids": [],
        "pinned_automation_ids": [],
    }


def _default_reading() -> dict[str, Any]:
    return {
        "width": "balanced",
        "spacing": "comfortable",
        "code_size": 14,
        "contrast": "standard",
        "font": "system",
    }


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        now = time.time()
        defaults = (
            ("work", "Trabalho", "work"),
            ("study", "Estudo", "study"),
            ("personal", "Pessoal", "personal"),
        )
        for profile_id, name, kind in defaults:
            connection.execute(
                """
                INSERT OR IGNORE INTO experience_profiles (
                    id, name, kind, home_json, reading_json, active,
                    protected, revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    profile_id,
                    name,
                    kind,
                    json.dumps(_default_home(kind), ensure_ascii=False),
                    json.dumps(_default_reading(), ensure_ascii=False),
                    int(profile_id == "work"),
                    now,
                    now,
                ),
            )
        active = connection.execute(
            "SELECT id FROM experience_profiles WHERE active = 1 LIMIT 1"
        ).fetchone()
        if active is None:
            connection.execute(
                "UPDATE experience_profiles SET active = 1 WHERE id = 'work'"
            )
        connection.commit()


def _loads(value: str, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return dict(fallback)
    return parsed if isinstance(parsed, dict) else dict(fallback)


def _dedupe_ids(
    values: Any,
    *,
    allowed: set[str] | None = None,
    limit: int = 50,
) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for value in values:
        item = str(value or "").strip()[:160]
        if not item or item in output:
            continue
        if allowed is not None and item not in allowed:
            continue
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _sanitize_home(value: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    base = fallback or _default_home("work")
    order = _dedupe_ids(
        source.get("module_order", base.get("module_order")),
        allowed=_MODULES,
        limit=len(_MODULES),
    )
    for module in base.get("module_order", []):
        if module in _MODULES and module not in order:
            order.append(module)
    return {
        "module_order": order,
        "hidden_modules": _dedupe_ids(
            source.get("hidden_modules", base.get("hidden_modules")),
            allowed=_MODULES,
            limit=len(_MODULES),
        ),
        "shortcut_ids": _dedupe_ids(
            source.get("shortcut_ids", base.get("shortcut_ids")),
            allowed=_SHORTCUTS,
            limit=8,
        ),
        "pinned_project_ids": _dedupe_ids(
            source.get("pinned_project_ids", base.get("pinned_project_ids")),
            limit=30,
        ),
        "pinned_automation_ids": _dedupe_ids(
            source.get(
                "pinned_automation_ids",
                base.get("pinned_automation_ids"),
            ),
            limit=30,
        ),
    }


def _sanitize_reading(
    value: Any,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    base = fallback or _default_reading()
    width = str(source.get("width", base.get("width", "balanced")))
    spacing = str(source.get("spacing", base.get("spacing", "comfortable")))
    contrast = str(source.get("contrast", base.get("contrast", "standard")))
    font = str(source.get("font", base.get("font", "system")))
    try:
        code_size = int(source.get("code_size", base.get("code_size", 14)))
    except (TypeError, ValueError):
        code_size = 14
    return {
        "width": width if width in _WIDTHS else "balanced",
        "spacing": spacing if spacing in _SPACINGS else "comfortable",
        "code_size": max(12, min(code_size, 22)),
        "contrast": contrast if contrast in _CONTRASTS else "standard",
        "font": font if font in _FONTS else "system",
    }


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "home": _sanitize_home(_loads(row["home_json"], {})),
        "reading": _sanitize_reading(_loads(row["reading_json"], {})),
        "active": bool(row["active"]),
        "protected": bool(row["protected"]),
        "revision": int(row["revision"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def list_profiles() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM experience_profiles
            ORDER BY active DESC, protected DESC, created_at, name
            """
        ).fetchall()
    return [_public(row) for row in rows]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM experience_profiles WHERE id = ?",
            (str(profile_id),),
        ).fetchone()
    return _public(row) if row else None


def get_active() -> dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM experience_profiles WHERE active = 1 LIMIT 1"
        ).fetchone()
    if row is None:
        _init_db()
        profile = get_profile("work")
        assert profile is not None
        return profile
    return _public(row)


def create_profile(
    *,
    name: str,
    kind: str = "custom",
    home: dict[str, Any] | None = None,
    reading: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()[:80]
    if not clean_name:
        raise ValueError("O nome do perfil é obrigatório.")
    clean_kind = re.sub(r"[^a-z0-9_-]+", "-", str(kind).lower()).strip("-")
    clean_kind = clean_kind[:40] or "custom"
    profile_id = f"profile-{uuid.uuid4().hex[:12]}"
    now = time.time()
    clean_home = _sanitize_home(home or {}, _default_home("work"))
    clean_reading = _sanitize_reading(reading or {}, _default_reading())
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO experience_profiles (
                id, name, kind, home_json, reading_json, active,
                protected, revision, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 1, ?, ?)
            """,
            (
                profile_id,
                clean_name,
                clean_kind,
                json.dumps(clean_home, ensure_ascii=False),
                json.dumps(clean_reading, ensure_ascii=False),
                now,
                now,
            ),
        )
        connection.commit()
    profile = get_profile(profile_id)
    assert profile is not None
    return profile


def update_profile(profile_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get_profile(profile_id)
    if current is None:
        raise KeyError(profile_id)
    clean: dict[str, Any] = {}
    if "name" in changes:
        name = str(changes.get("name") or "").strip()[:80]
        if not name:
            raise ValueError("O nome do perfil é obrigatório.")
        clean["name"] = name
    if "home" in changes:
        clean["home_json"] = json.dumps(
            _sanitize_home(changes.get("home"), current["home"]),
            ensure_ascii=False,
        )
    if "reading" in changes:
        clean["reading_json"] = json.dumps(
            _sanitize_reading(changes.get("reading"), current["reading"]),
            ensure_ascii=False,
        )
    if clean:
        assignments = ", ".join(f"{field} = ?" for field in clean)
        with _LOCK, _connect() as connection:
            connection.execute(
                f"""
                UPDATE experience_profiles
                SET {assignments}, revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                [*clean.values(), time.time(), profile_id],
            )
            connection.commit()
    profile = get_profile(profile_id)
    assert profile is not None
    return profile


def set_active(profile_id: str) -> dict[str, Any]:
    profile = get_profile(profile_id)
    if profile is None:
        raise KeyError(profile_id)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute("UPDATE experience_profiles SET active = 0 WHERE active = 1")
        connection.execute(
            """
            UPDATE experience_profiles
            SET active = 1, revision = revision + 1, updated_at = ?
            WHERE id = ?
            """,
            (now, profile_id),
        )
        connection.commit()
    active = get_profile(profile_id)
    assert active is not None
    return active


def delete_profile(profile_id: str) -> bool:
    profile = get_profile(profile_id)
    if profile is None:
        return False
    if profile["protected"]:
        raise ValueError("Os perfis Trabalho, Estudo e Pessoal não podem ser excluídos.")
    if profile["active"]:
        raise ValueError("Ative outro perfil antes de excluir este perfil.")
    with _LOCK, _connect() as connection:
        result = connection.execute(
            "DELETE FROM experience_profiles WHERE id = ?",
            (profile_id,),
        )
        connection.commit()
    return result.rowcount > 0


_init_db()
