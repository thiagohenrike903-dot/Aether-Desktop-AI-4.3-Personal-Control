"""Unified SQLite conversation history with branches and pagination."""
from __future__ import annotations

import base64
import json
import math
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings
from .redaction import is_sensitive_field, redact_text

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "conversations.sqlite3"
_ROLES = {"user", "assistant", "system", "tool"}
_MAX_METADATA_BYTES = 1_500_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    project_id  TEXT,
    title       TEXT NOT NULL,
    favorite    INTEGER NOT NULL DEFAULT 0,
    tags_json   TEXT NOT NULL DEFAULT '[]',
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conversations_updated
ON conversations(archived, updated_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS conversation_messages (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    parent_id        TEXT,
    branch_id        TEXT NOT NULL,
    metadata_json    TEXT NOT NULL DEFAULT '{}',
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_conversation_messages
ON conversation_messages(conversation_id, branch_id, created_at, id);
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


def _encode_cursor(ts: float, item_id: str) -> str:
    payload = json.dumps([ts, item_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[float, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        return float(value[0]), str(value[1])
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        raise ValueError("Cursor inválido.")


def _clean_tags(tags: list[str] | None) -> list[str]:
    output: list[str] = []
    for item in tags or []:
        value = str(item).strip()[:60]
        if value and value not in output:
            output.append(value)
    return output[:30]


def _safe_metadata_value(
    value: Any,
    *,
    key: str = "",
    depth: int = 0,
) -> Any:
    if depth > 7:
        return "[limite de profundidade]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:120]:
            child_key = str(raw_key)[:160]
            if not child_key:
                continue
            output[child_key] = (
                "[redigido]"
                if is_sensitive_field(child_key)
                else _safe_metadata_value(
                    item,
                    key=child_key,
                    depth=depth + 1,
                )
            )
        return output
    if isinstance(value, list):
        return [
            _safe_metadata_value(item, key=key, depth=depth + 1)
            for item in value[:100]
        ]
    if isinstance(value, str):
        limit = 200_000 if key in {"content", "response", "reply"} else 20_000
        return redact_text(value)[:limit]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    return redact_text(value)[:2_000]


def _sanitize_metadata(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    output = _safe_metadata_value(source)
    if not isinstance(output, dict):
        return {}
    encoded = json.dumps(
        output,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
        raise ValueError("Os metadados da mensagem excedem o limite seguro.")
    return output


def _public_conversation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "favorite": bool(row["favorite"]),
        "tags": json.loads(row["tags_json"] or "[]"),
        "archived": bool(row["archived"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message_count": row["message_count"] if "message_count" in row.keys() else 0,
    }


def create(
    *,
    title: str = "Nova conversa",
    project_id: str | None = None,
    tags: list[str] | None = None,
    favorite: bool = False,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    conversation_id = str(conversation_id or uuid.uuid4())
    title = str(title or "Nova conversa").strip()[:240] or "Nova conversa"
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO conversations (
                id, project_id, title, favorite, tags_json,
                archived, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                conversation_id,
                project_id,
                title,
                int(favorite),
                json.dumps(_clean_tags(tags), ensure_ascii=False),
                now,
                now,
            ),
        )
        connection.commit()
    item = get(conversation_id)
    assert item is not None
    return item


def get(conversation_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT c.*, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN conversation_messages m ON m.conversation_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (conversation_id,),
        ).fetchone()
    return _public_conversation(row) if row else None


def list_conversations(
    *,
    project_id: str | None = None,
    archived: bool | None = False,
    favorite: bool | None = None,
    tag: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    clauses: list[str] = []
    values: list[Any] = []
    if project_id is not None:
        clauses.append("c.project_id = ?")
        values.append(project_id)
    if archived is not None:
        clauses.append("c.archived = ?")
        values.append(int(archived))
    if favorite is not None:
        clauses.append("c.favorite = ?")
        values.append(int(favorite))
    if tag:
        clauses.append("c.tags_json LIKE ?")
        values.append(f'%"{str(tag)[:60]}"%')
    decoded = _decode_cursor(cursor)
    if decoded:
        clauses.append("(c.updated_at < ? OR (c.updated_at = ? AND c.id < ?))")
        values.extend([decoded[0], decoded[0], decoded[1]])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(safe_limit + 1)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT c.*, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN conversation_messages m ON m.conversation_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    next_cursor = (
        _encode_cursor(rows[-1]["updated_at"], rows[-1]["id"])
        if has_more and rows
        else None
    )
    return {
        "conversations": [_public_conversation(row) for row in rows],
        "next_cursor": next_cursor,
    }


def update(conversation_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get(conversation_id)
    if current is None:
        raise KeyError(conversation_id)
    clean: dict[str, Any] = {}
    if "title" in changes:
        clean["title"] = str(changes["title"] or "").strip()[:240] or "Nova conversa"
    if "project_id" in changes:
        clean["project_id"] = changes["project_id"] or None
    if "favorite" in changes:
        clean["favorite"] = int(bool(changes["favorite"]))
    if "archived" in changes:
        clean["archived"] = int(bool(changes["archived"]))
    if "tags" in changes:
        clean["tags_json"] = json.dumps(
            _clean_tags(changes["tags"]),
            ensure_ascii=False,
        )
    if clean:
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with _LOCK, _connect() as connection:
            connection.execute(
                f"UPDATE conversations SET {assignments}, updated_at = ? WHERE id = ?",
                [*clean.values(), time.time(), conversation_id],
            )
            connection.commit()
    item = get(conversation_id)
    assert item is not None
    return item


def delete(conversation_id: str, *, permanent: bool = False) -> bool:
    if get(conversation_id) is None:
        return False
    if not permanent:
        update(conversation_id, {"archived": True})
        return True
    with _LOCK, _connect() as connection:
        connection.execute(
            "DELETE FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        result = connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        connection.commit()
    return result.rowcount > 0


def _public_message(row: sqlite3.Row) -> dict[str, Any]:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "parent_id": row["parent_id"],
        "branch_id": row["branch_id"],
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def add_message(
    conversation_id: str,
    *,
    role: str,
    content: str,
    parent_id: str | None = None,
    branch_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversation = get(conversation_id)
    if conversation is None:
        raise KeyError(conversation_id)
    role = str(role or "").strip().lower()
    if role not in _ROLES:
        raise ValueError("Papel de mensagem inválido.")
    content = str(content or "")
    if not content.strip() or len(content) > 200_000:
        raise ValueError("A mensagem está vazia ou excede o limite.")
    if parent_id:
        parent = get_message(conversation_id, parent_id)
        if parent is None:
            raise ValueError("Mensagem pai não encontrada.")
        if not branch_id:
            branch_id = parent["branch_id"]
    branch_id = str(branch_id or "main")[:160]
    message_id = str(uuid.uuid4())
    now = time.time()
    safe_metadata = _sanitize_metadata(metadata)
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, role, content, parent_id,
                branch_id, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                content,
                parent_id,
                branch_id,
                json.dumps(safe_metadata, ensure_ascii=False, default=str),
                now,
                now,
            ),
        )
        title = conversation["title"]
        if (
            role == "user"
            and conversation["message_count"] == 0
            and title == "Nova conversa"
        ):
            title = content.strip().splitlines()[0][:72] or title
        connection.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conversation_id),
        )
        connection.commit()
    item = get_message(conversation_id, message_id)
    assert item is not None
    return item


def get_message(conversation_id: str, message_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM conversation_messages
            WHERE conversation_id = ? AND id = ?
            """,
            (conversation_id, message_id),
        ).fetchone()
    return _public_message(row) if row else None


def list_messages(
    conversation_id: str,
    *,
    branch_id: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    if get(conversation_id) is None:
        raise KeyError(conversation_id)
    safe_limit = max(1, min(int(limit), 500))
    clauses = ["conversation_id = ?"]
    values: list[Any] = [conversation_id]
    if branch_id:
        clauses.append("branch_id = ?")
        values.append(branch_id)
    decoded = _decode_cursor(cursor)
    if decoded:
        clauses.append("(created_at > ? OR (created_at = ? AND id > ?))")
        values.extend([decoded[0], decoded[0], decoded[1]])
    values.append(safe_limit + 1)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM conversation_messages
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at, id
            LIMIT ?
            """,
            values,
        ).fetchall()
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    next_cursor = (
        _encode_cursor(rows[-1]["created_at"], rows[-1]["id"])
        if has_more and rows
        else None
    )
    return {
        "messages": [_public_message(row) for row in rows],
        "next_cursor": next_cursor,
    }


def context_history(
    conversation_id: str,
    *,
    parent_message_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 30,
    max_chars: int = 48_000,
) -> list[dict[str, Any]]:
    """Return the exact bounded message history used for a new response.

    When a parent is supplied we follow its ancestry, which is the only
    reliable way to isolate an in-conversation branch. Older clients normally
    send only ``branch_id``; for them we read the most recent messages from
    that branch. The default branch is ``main``.
    """
    if get(conversation_id) is None:
        raise KeyError(conversation_id)
    safe_limit = max(1, min(int(limit), 100))
    safe_chars = max(1_000, min(int(max_chars), 200_000))
    selected: list[dict[str, Any]] = []

    if parent_message_id:
        seen: set[str] = set()
        current_id: str | None = str(parent_message_id)
        while current_id and len(selected) < safe_limit:
            if current_id in seen:
                raise ValueError("A linhagem da conversa contém um ciclo.")
            seen.add(current_id)
            item = get_message(conversation_id, current_id)
            if item is None:
                raise ValueError("Mensagem pai não encontrada.")
            selected.append(item)
            current_id = item.get("parent_id")
        selected.reverse()
    else:
        selected_branch = str(branch_id or "main")[:160]
        with _LOCK, _connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ? AND branch_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (conversation_id, selected_branch, safe_limit),
            ).fetchall()
        selected = [_public_message(row) for row in reversed(rows)]

    # Keep the newest complete turns when the character budget is exceeded.
    bounded: list[dict[str, Any]] = []
    used_chars = 0
    for item in reversed(selected):
        content = str(item.get("content") or "")
        if bounded and used_chars + len(content) > safe_chars:
            break
        if not bounded and len(content) > safe_chars:
            content = content[-safe_chars:]
            item = {**item, "content": content, "context_truncated": True}
        bounded.append(item)
        used_chars += len(content)
    bounded.reverse()
    return bounded


def update_message(
    conversation_id: str,
    message_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    current = get_message(conversation_id, message_id)
    if current is None:
        raise KeyError(message_id)
    clean: dict[str, Any] = {}
    if "content" in changes:
        content = str(changes["content"] or "")
        if not content.strip() or len(content) > 200_000:
            raise ValueError("A mensagem está vazia ou excede o limite.")
        clean["content"] = content
    if "metadata" in changes:
        clean["metadata_json"] = json.dumps(
            _sanitize_metadata(changes["metadata"]),
            ensure_ascii=False,
            default=str,
        )
    if clean:
        assignments = ", ".join(f"{key} = ?" for key in clean)
        with _LOCK, _connect() as connection:
            connection.execute(
                f"""
                UPDATE conversation_messages
                SET {assignments}, updated_at = ?
                WHERE conversation_id = ? AND id = ?
                """,
                [*clean.values(), time.time(), conversation_id, message_id],
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (time.time(), conversation_id),
            )
            connection.commit()
    item = get_message(conversation_id, message_id)
    assert item is not None
    return item


def delete_message(conversation_id: str, message_id: str) -> bool:
    with _LOCK, _connect() as connection:
        result = connection.execute(
            """
            DELETE FROM conversation_messages
            WHERE conversation_id = ? AND id = ?
            """,
            (conversation_id, message_id),
        )
        if result.rowcount:
            connection.execute(
                """
                UPDATE conversation_messages
                SET parent_id = NULL
                WHERE conversation_id = ? AND parent_id = ?
                """,
                (conversation_id, message_id),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (time.time(), conversation_id),
            )
        connection.commit()
    return result.rowcount > 0
