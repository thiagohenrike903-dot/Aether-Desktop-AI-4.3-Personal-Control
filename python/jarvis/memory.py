"""Memory subsystem.

Three layers:
  - **Short term**: rolling window of the last N turns in SQLite, exposed
    synchronously for the FastAPI layer.
  - **Long term**: every turn is also written here, so the assistant can
    recall prior sessions.
  - **Vector**: turns and explicit "facts" are embedded with sentence-
    transformers and stored in ChromaDB. ``recall`` runs a semantic query
    against this store and returns the top-k matches.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings

# --------------------------------------------------------------------------- #
# Short + long term (SQLite)
# --------------------------------------------------------------------------- #

_LOCK = threading.Lock()
_SHORT_TERM_WINDOW = 30  # number of recent turns to return to the model

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          TEXT PRIMARY KEY,
    ts          REAL NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT,
    session_id  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_turns_session ON turns(session_id, ts);
CREATE TABLE IF NOT EXISTS facts (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    ts          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    ts          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS project_memories (
    id           TEXT PRIMARY KEY,
    project_root TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'note',
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_project_memory_key
ON project_memories(project_root, kind, key);
CREATE TABLE IF NOT EXISTS memory_items (
    id          TEXT PRIMARY KEY,
    scope       TEXT NOT NULL,
    project_id  TEXT,
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_memory_item_key
ON memory_items(scope, IFNULL(project_id, ''), kind, key);
CREATE INDEX IF NOT EXISTS ix_memory_items_scope
ON memory_items(scope, project_id, enabled, updated_at DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.short_term_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _LOCK, _connect() as c:
        for stmt in _SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                c.execute(s)
        # Migrate 4.0 memories into the editable 4.1 table. The legacy tables
        # remain in place so older installations can be upgraded in-place.
        now = time.time()
        for row in c.execute("SELECT key, value, ts FROM facts").fetchall():
            c.execute(
                """
                INSERT OR IGNORE INTO memory_items
                    (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
                VALUES (?, 'global', NULL, 'fact', ?, ?, 1, ?, ?)
                """,
                (f"fact:{row['key']}", row["key"], row["value"], row["ts"], row["ts"]),
            )
        for row in c.execute("SELECT key, value, ts FROM preferences").fetchall():
            c.execute(
                """
                INSERT OR IGNORE INTO memory_items
                    (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
                VALUES (?, 'global', NULL, 'preference', ?, ?, 1, ?, ?)
                """,
                (
                    f"preference:{row['key']}",
                    row["key"],
                    row["value"],
                    row["ts"],
                    row["ts"],
                ),
            )
        for row in c.execute(
            """
            SELECT id, project_root, kind, key, value, created_at, updated_at
            FROM project_memories
            """
        ).fetchall():
            c.execute(
                """
                INSERT OR IGNORE INTO memory_items
                    (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
                VALUES (?, 'project', ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    row["id"],
                    row["project_root"],
                    row["kind"],
                    row["key"],
                    row["value"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
        c.commit()


_init_db()


def add_turn(role: str, content: str, session_id: str, metadata: dict[str, Any] | None = None) -> str:
    turn_id = str(uuid.uuid4())
    with _LOCK, _connect() as c:
        c.execute(
            "INSERT INTO turns (id, ts, role, content, metadata, session_id) VALUES (?, ?, ?, ?, ?, ?)",
            (turn_id, time.time(), role, content, json.dumps(metadata or {}), session_id),
        )
        c.commit()
    return turn_id


def get_short_term_history(session_id: str, limit: int = _SHORT_TERM_WINDOW) -> list[dict[str, Any]]:
    with _LOCK, _connect() as c:
        rows = c.execute(
            "SELECT id, ts, role, content, metadata FROM turns WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in reversed(rows):
        out.append({
            "id": r["id"],
            "ts": r["ts"],
            "role": r["role"],
            "content": r["content"],
            "metadata": json.loads(r["metadata"] or "{}"),
        })
    return out


def get_long_term(limit: int = 200) -> list[dict[str, Any]]:
    with _LOCK, _connect() as c:
        rows = c.execute(
            "SELECT id, ts, role, content, metadata, session_id FROM turns ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
    """Return compact conversation summaries ordered by recent activity."""
    safe_limit = max(1, min(int(limit), 200))
    with _LOCK, _connect() as c:
        rows = c.execute(
            """
            WITH grouped AS (
                SELECT
                    session_id,
                    MIN(ts) AS created_at,
                    MAX(ts) AS updated_at,
                    COUNT(*) AS turn_count
                FROM turns
                GROUP BY session_id
                ORDER BY updated_at DESC
                LIMIT ?
            )
            SELECT
                grouped.session_id,
                grouped.created_at,
                grouped.updated_at,
                grouped.turn_count,
                (
                    SELECT content
                    FROM turns first_turn
                    WHERE first_turn.session_id = grouped.session_id
                      AND first_turn.role = 'user'
                    ORDER BY first_turn.ts ASC
                    LIMIT 1
                ) AS first_message,
                (
                    SELECT content
                    FROM turns last_turn
                    WHERE last_turn.session_id = grouped.session_id
                    ORDER BY last_turn.ts DESC
                    LIMIT 1
                ) AS last_message
            FROM grouped
            ORDER BY grouped.updated_at DESC
            """,
            (safe_limit,),
        ).fetchall()

    sessions: list[dict[str, Any]] = []
    for row in rows:
        first_message = str(row["first_message"] or "Nova conversa").strip()
        last_message = str(row["last_message"] or "").strip()
        title = first_message.splitlines()[0][:72] or "Nova conversa"
        sessions.append({
            "session_id": row["session_id"],
            "title": title,
            "preview": last_message.replace("\n", " ")[:140],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "turn_count": row["turn_count"],
        })
    return sessions


_SENSITIVE_KEY_PARTS = {
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "credential", "private_key", "access_key",
}


def _reject_sensitive(key: str, value: str) -> None:
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        raise ValueError("Informações sensíveis não podem ser salvas na memória.")
    compact = value.strip()
    if (
        compact.startswith(("sk-", "ghp_", "github_pat_", "AIza"))
        or "-----BEGIN PRIVATE KEY-----" in compact
    ):
        raise ValueError("O valor parece conter uma credencial e não foi salvo.")


def set_fact(key: str, value: str) -> None:
    _reject_sensitive(key, value)
    key = key.strip()
    value = value.strip()
    if not key or not value:
        raise ValueError("Chave e valor são obrigatórios.")
    if len(key) > 240 or len(value) > 20_000:
        raise ValueError("A memória excede o limite permitido.")
    now = time.time()
    with _LOCK, _connect() as c:
        c.execute(
            "INSERT INTO facts (key, value, ts) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
            (key, value, now),
        )
        c.execute(
            """
            INSERT INTO memory_items
                (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
            VALUES (?, 'global', NULL, 'fact', ?, ?, 1, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET value = excluded.value, enabled = 1, updated_at = excluded.updated_at
            """,
            (f"fact:{key}", key, value, now, now),
        )
        c.commit()


def get_facts(prefix: str | None = None) -> dict[str, str]:
    with _LOCK, _connect() as c:
        if prefix:
            rows = c.execute(
                """
                SELECT key, value FROM memory_items
                WHERE scope = 'global' AND kind = 'fact' AND enabled = 1
                  AND key LIKE ?
                """,
                (f"{prefix}%",),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT key, value FROM memory_items
                WHERE scope = 'global' AND kind = 'fact' AND enabled = 1
                """
            ).fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_preference(key: str, value: str) -> None:
    _reject_sensitive(key, value)
    key = key.strip()
    value = value.strip()
    if not key or not value:
        raise ValueError("Chave e valor são obrigatórios.")
    if len(key) > 240 or len(value) > 20_000:
        raise ValueError("A memória excede o limite permitido.")
    now = time.time()
    with _LOCK, _connect() as c:
        c.execute(
            "INSERT INTO preferences (key, value, ts) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
            (key, value, now),
        )
        c.execute(
            """
            INSERT INTO memory_items
                (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
            VALUES (?, 'global', NULL, 'preference', ?, ?, 1, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET value = excluded.value, enabled = 1, updated_at = excluded.updated_at
            """,
            (f"preference:{key}", key, value, now, now),
        )
        c.commit()


def get_preferences() -> dict[str, str]:
    with _LOCK, _connect() as c:
        rows = c.execute(
            """
            SELECT key, value FROM memory_items
            WHERE scope = 'global' AND kind = 'preference' AND enabled = 1
            """
        ).fetchall()
    return {r["key"]: r["value"] for r in rows}


def delete_turn(turn_id: str) -> bool:
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM turns WHERE id = ?", (turn_id,))
        c.commit()
        return result.rowcount > 0


def clear_session(session_id: str) -> int:
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        c.commit()
        return result.rowcount


def delete_fact(key: str) -> bool:
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM facts WHERE key = ?", (key,))
        memory_result = c.execute(
            "DELETE FROM memory_items WHERE id = ?",
            (f"fact:{key}",),
        )
        c.commit()
        return result.rowcount > 0 or memory_result.rowcount > 0


def delete_preference(key: str) -> bool:
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM preferences WHERE key = ?", (key,))
        memory_result = c.execute(
            "DELETE FROM memory_items WHERE id = ?",
            (f"preference:{key}",),
        )
        c.commit()
        return result.rowcount > 0 or memory_result.rowcount > 0


def list_project_memories(
    project_root: str,
    *,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    with _LOCK, _connect() as c:
        rows = c.execute(
            f"""
            SELECT
                id,
                project_id AS project_root,
                kind,
                key,
                value,
                enabled,
                created_at,
                updated_at
            FROM memory_items
            WHERE scope = 'project' AND project_id = ?
              {" " if include_disabled else "AND enabled = 1"}
            ORDER BY updated_at DESC
            """,
            (project_root,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_project_memory(
    project_root: str,
    key: str,
    value: str,
    kind: str = "note",
) -> dict[str, Any]:
    project_root = project_root.strip()
    key = key.strip()
    value = value.strip()
    kind = kind.strip() or "note"
    if not project_root or not key or not value:
        raise ValueError("Projeto, chave e valor são obrigatórios.")
    if len(key) > 240 or len(value) > 20_000:
        raise ValueError("A memória excede o limite permitido.")
    if kind not in {"note", "decision", "constraint", "summary"}:
        raise ValueError("Tipo de memória de projeto inválido.")
    _reject_sensitive(key, value)
    now = time.time()
    memory_id = str(uuid.uuid4())
    with _LOCK, _connect() as c:
        existing = c.execute(
            """
            SELECT id, created_at FROM memory_items
            WHERE scope = 'project' AND project_id = ? AND kind = ? AND key = ?
            """,
            (project_root, kind, key),
        ).fetchone()
        if existing:
            memory_id = existing["id"]
            created_at = existing["created_at"]
        else:
            created_at = now
        c.execute(
            """
            INSERT INTO memory_items
                (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
            VALUES (?, 'project', ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET value = excluded.value, enabled = 1, updated_at = excluded.updated_at
            """,
            (memory_id, project_root, kind, key, value, created_at, now),
        )
        c.commit()
    return {
        "id": memory_id,
        "project_root": project_root,
        "kind": kind,
        "key": key,
        "value": value,
        "created_at": created_at,
        "updated_at": now,
    }


def delete_project_memory(memory_id: str) -> bool:
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM project_memories WHERE id = ?", (memory_id,))
        memory_result = c.execute(
            "DELETE FROM memory_items WHERE id = ? AND scope = 'project'",
            (memory_id,),
        )
        c.commit()
        return result.rowcount > 0 or memory_result.rowcount > 0


_MEMORY_KINDS = {
    "fact",
    "preference",
    "note",
    "decision",
    "constraint",
    "summary",
}


def list_memories(
    *,
    scope: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    enabled: bool | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if scope is not None:
        if scope not in {"global", "project"}:
            raise ValueError("Escopo de memória inválido.")
        clauses.append("scope = ?")
        values.append(scope)
    if project_id is not None:
        clauses.append("project_id = ?")
        values.append(project_id)
    if kind is not None:
        if kind not in _MEMORY_KINDS:
            raise ValueError("Tipo de memória inválido.")
        clauses.append("kind = ?")
        values.append(kind)
    if enabled is not None:
        clauses.append("enabled = ?")
        values.append(int(enabled))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(max(1, min(int(limit), 2_000)))
    with _LOCK, _connect() as c:
        rows = c.execute(
            f"""
            SELECT id, scope, project_id, kind, key, value, enabled,
                   created_at, updated_at
            FROM memory_items
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            values,
        ).fetchall()
    return [
        {
            **dict(row),
            "enabled": bool(row["enabled"]),
        }
        for row in rows
    ]


def create_memory(
    *,
    scope: str,
    kind: str,
    key: str,
    value: str,
    project_id: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    scope = scope.strip().lower()
    kind = kind.strip().lower()
    key = key.strip()
    value = value.strip()
    if scope not in {"global", "project"}:
        raise ValueError("Escopo de memória inválido.")
    if kind not in _MEMORY_KINDS:
        raise ValueError("Tipo de memória inválido.")
    if scope == "project" and not str(project_id or "").strip():
        raise ValueError("Memórias de projeto exigem project_id.")
    if scope == "global":
        project_id = None
    if not key or not value:
        raise ValueError("Chave e valor são obrigatórios.")
    if len(key) > 240 or len(value) > 20_000:
        raise ValueError("A memória excede o limite permitido.")
    _reject_sensitive(key, value)
    if scope == "global" and kind == "fact":
        set_fact(key, value)
        memory_id = f"fact:{key}"
    elif scope == "global" and kind == "preference":
        set_preference(key, value)
        memory_id = f"preference:{key}"
    elif scope == "project" and kind in {"note", "decision", "constraint", "summary"}:
        memory_id = set_project_memory(str(project_id), key, value, kind)["id"]
    else:
        now = time.time()
        memory_id = str(uuid.uuid4())
        with _LOCK, _connect() as c:
            existing = c.execute(
                """
                SELECT id FROM memory_items
                WHERE scope = ? AND IFNULL(project_id, '') = IFNULL(?, '')
                  AND kind = ? AND key = ?
                """,
                (scope, project_id, kind, key),
            ).fetchone()
            if existing:
                raise ValueError("Já existe uma memória com esta chave e tipo.")
            c.execute(
                """
                INSERT INTO memory_items
                    (id, scope, project_id, kind, key, value, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    scope,
                    project_id,
                    kind,
                    key,
                    value,
                    int(enabled),
                    now,
                    now,
                ),
            )
            c.commit()
    if not enabled:
        update_memory(memory_id, enabled=False)
    item = get_memory(memory_id)
    assert item is not None
    return item


def get_memory(memory_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as c:
        row = c.execute(
            """
            SELECT id, scope, project_id, kind, key, value, enabled,
                   created_at, updated_at
            FROM memory_items
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()
    if not row:
        return None
    return {**dict(row), "enabled": bool(row["enabled"])}


def update_memory(
    memory_id: str,
    *,
    key: str | None = None,
    value: str | None = None,
    kind: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    current = get_memory(memory_id)
    if current is None:
        raise KeyError(memory_id)
    next_key = str(key if key is not None else current["key"]).strip()
    next_value = str(value if value is not None else current["value"]).strip()
    next_kind = str(kind if kind is not None else current["kind"]).strip().lower()
    if not next_key or not next_value:
        raise ValueError("Chave e valor são obrigatórios.")
    if len(next_key) > 240 or len(next_value) > 20_000:
        raise ValueError("A memória excede o limite permitido.")
    if next_kind not in _MEMORY_KINDS:
        raise ValueError("Tipo de memória inválido.")
    _reject_sensitive(next_key, next_value)
    now = time.time()
    next_id = memory_id
    if current["scope"] == "global" and next_kind in {"fact", "preference"}:
        next_id = f"{next_kind}:{next_key}"
    with _LOCK, _connect() as c:
        try:
            c.execute(
                """
                UPDATE memory_items
                SET id = ?, key = ?, value = ?, kind = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_id,
                    next_key,
                    next_value,
                    next_kind,
                    int(current["enabled"] if enabled is None else enabled),
                    now,
                    memory_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Já existe uma memória com esta chave e tipo.") from exc
        # Keep legacy tables aligned for old clients.
        if current["scope"] == "global" and current["kind"] == "fact":
            c.execute("DELETE FROM facts WHERE key = ?", (current["key"],))
        elif current["scope"] == "global" and current["kind"] == "preference":
            c.execute("DELETE FROM preferences WHERE key = ?", (current["key"],))
        if current["scope"] == "global" and next_kind == "fact":
            c.execute(
                """
                INSERT INTO facts (key, value, ts) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, ts = excluded.ts
                """,
                (next_key, next_value, now),
            )
        elif current["scope"] == "global" and next_kind == "preference":
            c.execute(
                """
                INSERT INTO preferences (key, value, ts) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, ts = excluded.ts
                """,
                (next_key, next_value, now),
            )
        c.commit()
    item = get_memory(next_id)
    assert item is not None
    return item


def delete_memory(memory_id: str) -> bool:
    current = get_memory(memory_id)
    if current is None:
        return False
    with _LOCK, _connect() as c:
        result = c.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
        if current["scope"] == "global" and current["kind"] == "fact":
            c.execute("DELETE FROM facts WHERE key = ?", (current["key"],))
        elif current["scope"] == "global" and current["kind"] == "preference":
            c.execute("DELETE FROM preferences WHERE key = ?", (current["key"],))
        elif current["scope"] == "project":
            c.execute("DELETE FROM project_memories WHERE id = ?", (memory_id,))
        c.commit()
    return result.rowcount > 0


def overview(session_id: str, project_root: str | None = None) -> dict[str, Any]:
    return {
        "conversation": get_short_term_history(session_id, 100),
        "facts": get_facts(),
        "preferences": get_preferences(),
        "project": list_project_memories(project_root) if project_root else [],
    }


# --------------------------------------------------------------------------- #
# Vector store (ChromaDB + sentence-transformers)
# --------------------------------------------------------------------------- #

class _VectorStore:
    """Lazy-loaded wrapper around ChromaDB + sentence-transformers.

    We import these heavy libraries lazily so the FastAPI service starts
    even when the vector dependencies aren't installed (e.g. CI smoke).
    """

    def __init__(self) -> None:
        self._client = None
        self._collection = None
        self._model = None

    def _ensure(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Vector store unavailable. Install chromadb and sentence-transformers "
                "to enable semantic memory."
            ) from exc

        self._client = chromadb.PersistentClient(path=str(settings.vector_db_path))
        self._collection = self._client.get_or_create_collection(
            name="jarvis_memory",
            metadata={"hnsw:space": "cosine"},
        )
        self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._ensure()
        embedding = self._model.encode([text])[0].tolist()  # type: ignore[union-attr]
        self._collection.upsert(  # type: ignore[union-attr]
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata or {}],
        )

    def query(self, text: str, n_results: int = 5) -> list[dict[str, Any]]:
        self._ensure()
        embedding = self._model.encode([text])[0].tolist()  # type: ignore[union-attr]
        res = self._collection.query(  # type: ignore[union-attr]
            query_embeddings=[embedding],
            n_results=n_results,
        )
        out: list[dict[str, Any]] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, d, m, dist in zip(ids, docs, metas, dists):
            out.append({"id": i, "document": d, "metadata": m, "score": 1 - dist})
        return out


vector_store = _VectorStore()
