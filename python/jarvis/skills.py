"""Persistent, versioned skills for Aether.

Skills are prompt-level capabilities: instructions, examples, rules and
knowledge references that can be global or scoped to a selected project.
They do not fine-tune a model and never grant new operating-system
permissions.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from typing import Any

from .config import settings

_DB_PATH = settings.data_dir / "skills.sqlite3"
_LOCK = threading.RLock()
_LIST_FIELDS = (
    "rules", "examples", "knowledge_files", "allowed_tools",
    "technologies", "triggers",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    rules TEXT NOT NULL DEFAULT '[]',
    examples TEXT NOT NULL DEFAULT '[]',
    knowledge_files TEXT NOT NULL DEFAULT '[]',
    allowed_tools TEXT NOT NULL DEFAULT '[]',
    technologies TEXT NOT NULL DEFAULT '[]',
    triggers TEXT NOT NULL DEFAULT '[]',
    priority INTEGER NOT NULL DEFAULT 50,
    version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    category TEXT NOT NULL DEFAULT 'Geral',
    scope TEXT NOT NULL DEFAULT 'global',
    project_root TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_revisions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_skills_scope ON skills(scope, project_root, enabled);
CREATE INDEX IF NOT EXISTS ix_skill_revisions ON skill_revisions(skill_id, version);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as conn:
        for statement in _SCHEMA.strip().split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.commit()


_init()


def _loads(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _skill(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for field in _LIST_FIELDS:
        item[field] = _loads(item.get(field))
    item["enabled"] = bool(item.get("enabled"))
    return item


def _serialisable(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload)
    for field in _LIST_FIELDS:
        value = item.get(field, [])
        if isinstance(value, str):
            value = [line.strip() for line in value.splitlines() if line.strip()]
        item[field] = [str(value_item) for value_item in (value or [])]
    return item


def _validate(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    item = _serialisable(payload)
    if not partial or "name" in item:
        item["name"] = str(item.get("name", "")).strip()
        if not item["name"]:
            raise ValueError("A skill precisa de um nome.")
    for field in ("description", "instructions", "category", "scope"):
        if field in item:
            item[field] = str(item.get(field) or "").strip()
    if "scope" in item and item["scope"] not in {"global", "project"}:
        raise ValueError("O escopo precisa ser global ou project.")
    if item.get("scope") == "project" and not item.get("project_root"):
        raise ValueError("Skills de projeto precisam de um projeto associado.")
    if "priority" in item:
        item["priority"] = max(0, min(100, int(item["priority"])))
    if "enabled" in item:
        item["enabled"] = bool(item["enabled"])
    return item


def _snapshot(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    data = _skill(row)
    conn.execute(
        "INSERT INTO skill_revisions (id, skill_id, version, snapshot, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), data["id"], data["version"], json.dumps(data, ensure_ascii=False), time.time()),
    )


def list_skills(project_root: str | None = None, include_disabled: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM skills"
    params: list[Any] = []
    clauses: list[str] = []
    if not include_disabled:
        clauses.append("enabled = 1")
    if project_root:
        clauses.append("(scope = 'global' OR project_root = ?)")
        params.append(project_root)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY enabled DESC, priority DESC, name COLLATE NOCASE"
    with _LOCK, _connect() as conn:
        return [_skill(row) for row in conn.execute(query, params).fetchall()]


def get_skill(skill_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
    return _skill(row) if row else None


def create_skill(payload: dict[str, Any]) -> dict[str, Any]:
    item = _validate(payload)
    now = time.time()
    skill_id = str(uuid.uuid4())
    values = {
        "id": skill_id,
        "name": item["name"],
        "description": item.get("description", ""),
        "instructions": item.get("instructions", ""),
        "priority": item.get("priority", 50),
        "enabled": 1 if item.get("enabled", True) else 0,
        "category": item.get("category", "Geral") or "Geral",
        "scope": item.get("scope", "global") or "global",
        "project_root": item.get("project_root"),
        "created_at": now,
        "updated_at": now,
    }
    for field in _LIST_FIELDS:
        values[field] = json.dumps(item.get(field, []), ensure_ascii=False)
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with _LOCK, _connect() as conn:
        conn.execute(
            f"INSERT INTO skills ({columns}, version) VALUES ({placeholders}, 1)",
            tuple(values.values()),
        )
        conn.commit()
    return get_skill(skill_id) or {}


def update_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = _validate(payload, partial=True)
    with _LOCK, _connect() as conn:
        current = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if not current:
            raise ValueError("Skill não encontrada.")
        _snapshot(conn, current)
        allowed = {
            "name", "description", "instructions", "priority", "enabled",
            "category", "scope", "project_root", *_LIST_FIELDS,
        }
        updates: dict[str, Any] = {}
        for key, value in item.items():
            if key not in allowed:
                continue
            if key in _LIST_FIELDS:
                updates[key] = json.dumps(value, ensure_ascii=False)
            elif key == "enabled":
                updates[key] = 1 if value else 0
            else:
                updates[key] = value
        updates["version"] = int(current["version"]) + 1
        updates["updated_at"] = time.time()
        assignment = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(
            f"UPDATE skills SET {assignment} WHERE id = ?",
            (*updates.values(), skill_id),
        )
        conn.commit()
    return get_skill(skill_id) or {}


def duplicate_skill(skill_id: str) -> dict[str, Any]:
    original = get_skill(skill_id)
    if not original:
        raise ValueError("Skill não encontrada.")
    copy = {key: value for key, value in original.items() if key not in {
        "id", "version", "created_at", "updated_at",
    }}
    copy["name"] = f"{original['name']} (cópia)"
    copy["enabled"] = False
    return create_skill(copy)


def delete_skill(skill_id: str, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "requires_confirmation": True}
    with _LOCK, _connect() as conn:
        current = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if not current:
            return {"ok": False, "error": "Skill não encontrada."}
        _snapshot(conn, current)
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        conn.commit()
    return {"ok": True, "deleted": skill_id}


def revisions(skill_id: str) -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT id, version, snapshot, created_at FROM skill_revisions WHERE skill_id = ? ORDER BY version DESC",
            (skill_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "version": row["version"],
            "created_at": row["created_at"],
            "snapshot": json.loads(row["snapshot"]),
        }
        for row in rows
    ]


def restore_revision(skill_id: str, revision_id: str) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT snapshot FROM skill_revisions WHERE id = ? AND skill_id = ?",
            (revision_id, skill_id),
        ).fetchone()
    if not row:
        raise ValueError("Versão não encontrada.")
    snapshot = json.loads(row["snapshot"])
    return update_skill(skill_id, snapshot)


def export_skills(skill_ids: list[str] | None = None) -> dict[str, Any]:
    items = list_skills()
    if skill_ids:
        selected = set(skill_ids)
        items = [item for item in items if item["id"] in selected]
    clean = [
        {key: value for key, value in item.items() if key not in {"id", "created_at", "updated_at"}}
        for item in items
    ]
    return {"format": "aether-skill-pack", "version": 1, "skills": clean}


def import_skills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("format") != "aether-skill-pack" or not isinstance(payload.get("skills"), list):
        raise ValueError("Arquivo de skills inválido.")
    created: list[dict[str, Any]] = []
    for raw in payload["skills"][:100]:
        if isinstance(raw, dict):
            created.append(create_skill(raw))
    return created


def match_skills(message: str, project_root: str | None = None) -> list[dict[str, Any]]:
    text = message.casefold()
    matched: list[tuple[int, dict[str, Any]]] = []
    for skill in list_skills(project_root, include_disabled=False):
        score = 0
        triggers = skill["triggers"] + skill["technologies"]
        for trigger in triggers:
            normalized = trigger.strip().casefold()
            if normalized and normalized in text:
                score += 4
        words = set(re.findall(r"[\w+#.-]{3,}", text))
        description_words = set(re.findall(
            r"[\w+#.-]{3,}",
            f"{skill['name']} {skill['description']}".casefold(),
        ))
        score += min(3, len(words & description_words))
        # A skill without explicit triggers is intentionally always-on within
        # its scope. Project skills are already filtered by project_root.
        if not triggers:
            score += 1
        if score:
            matched.append((score * 100 + int(skill["priority"]), skill))
    matched.sort(key=lambda pair: pair[0], reverse=True)
    return [skill for _, skill in matched[:6]]


def test_skill(skill_id: str, sample: str, project_root: str | None = None) -> dict[str, Any]:
    skill = get_skill(skill_id)
    if not skill:
        raise ValueError("Skill não encontrada.")
    matches = match_skills(sample, project_root)
    matched_ids = [item["id"] for item in matches]
    conflicts = [
        item for item in matches
        if item["id"] != skill_id and item["priority"] == skill["priority"]
    ]
    return {
        "ok": True,
        "matched": skill_id in matched_ids,
        "activation_order": [
            {"id": item["id"], "name": item["name"], "priority": item["priority"]}
            for item in matches
        ],
        "conflicts": [
            {"id": item["id"], "name": item["name"], "priority": item["priority"]}
            for item in conflicts
        ],
        "preview": skill["instructions"][:1200],
    }
