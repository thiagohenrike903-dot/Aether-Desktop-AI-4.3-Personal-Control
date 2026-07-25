"""Searchable, redacted audit ledger with a verifiable SHA-256 hash chain."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import settings
from .redaction import is_sensitive_field, redact_text

GENESIS_HASH = "0" * 64
_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_integrity_ledger (
    sequence         INTEGER PRIMARY KEY,
    id               TEXT NOT NULL UNIQUE,
    previous_hash    TEXT NOT NULL,
    entry_hash       TEXT NOT NULL UNIQUE,
    payload_json     TEXT NOT NULL,
    ts               REAL NOT NULL,
    operation_id     TEXT NOT NULL,
    event_id         TEXT NOT NULL UNIQUE,
    event_type       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    project_id       TEXT,
    resource_text    TEXT NOT NULL,
    site_text        TEXT NOT NULL,
    recipient_text   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_integrity_ts
ON audit_integrity_ledger(ts DESC);
CREATE INDEX IF NOT EXISTS ix_audit_integrity_kind
ON audit_integrity_ledger(kind, ts DESC);
CREATE INDEX IF NOT EXISTS ix_audit_integrity_project
ON audit_integrity_ledger(project_id, ts DESC);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path or _DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_db(db_path: Path | None = None) -> None:
    target = db_path or _DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect(target) as connection:
        connection.executescript(_SCHEMA)
        connection.commit()


_init_db()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _entry_hash(previous_hash: str, payload_json: str) -> str:
    return hashlib.sha256(
        f"{previous_hash}\n{payload_json}".encode("utf-8")
    ).hexdigest()


def _bounded_text(value: Any, limit: int = 2_000) -> str:
    text = redact_text(value or "")
    return text[:limit] + ("…" if len(text) > limit else "")


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "[limite de profundidade]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key)[:160]
            output[key] = (
                "[redigido]"
                if is_sensitive_field(key)
                else _safe_value(item, depth=depth + 1)
            )
        return output
    if isinstance(value, list):
        return [_safe_value(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return _bounded_text(value, 4_000)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _bounded_text(value, 1_000)


def _resource_dimensions(
    operation: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    affected = [
        _safe_value(item)
        for item in (operation.get("affected") or [])[:100]
        if isinstance(item, dict)
    ]
    resources: list[str] = []
    sites: list[str] = []
    recipients: list[str] = []
    for item in affected:
        item_type = str(item.get("type") or "").lower()
        values = [
            item.get("name"),
            item.get("path"),
            item.get("url"),
        ]
        resources.extend(
            _bounded_text(value, 500)
            for value in values
            if value not in (None, "")
        )
        if item_type == "site":
            value = item.get("name") or item.get("url")
            if value:
                sites.append(_bounded_text(value, 500))
        if item_type == "recipient":
            value = item.get("recipient") or item.get("name")
            if value:
                recipients.append(_bounded_text(value, 500))
    return (
        affected,
        list(dict.fromkeys(resources)),
        list(dict.fromkeys(sites)),
        list(dict.fromkeys(recipients)),
    )


def _project_id(operation: dict[str, Any]) -> str | None:
    action = operation.get("action")
    if not isinstance(action, dict):
        return None
    value = str(action.get("project_id") or "").strip()
    return value[:240] or None


def _row_public(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = None
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    state_change = None
    if isinstance(data, dict):
        if "before" in data or "after" in data:
            state_change = {
                "scope": "resource",
                "before": data.get("before"),
                "after": data.get("after"),
            }
        elif "from" in data or "to" in data:
            state_change = {
                "scope": "operation",
                "before": data.get("from"),
                "after": data.get("to"),
            }
    return {
        "sequence": int(row["sequence"]),
        "id": row["id"],
        "previous_hash": row["previous_hash"],
        "entry_hash": row["entry_hash"],
        "ts": float(row["ts"]),
        "operation_id": row["operation_id"],
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "kind": row["kind"],
        "project_id": row["project_id"],
        "resources": (
            payload.get("resources", []) if isinstance(payload, dict) else []
        ),
        "sites": payload.get("sites", []) if isinstance(payload, dict) else [],
        "recipients": (
            payload.get("recipients", []) if isinstance(payload, dict) else []
        ),
        "message": payload.get("message", "") if isinstance(payload, dict) else "",
        "data": data,
        "state_change": state_change,
        "integrity": "unverified",
    }


def append_operation_event(
    operation: dict[str, Any],
    event: dict[str, Any],
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Append one already-redacted Control Centre event to the chain."""
    target = db_path or _DB_PATH
    _init_db(target)
    event_id = str(event.get("id") or "").strip()
    operation_id = str(
        event.get("operation_id") or operation.get("id") or ""
    ).strip()
    if not event_id or not operation_id:
        raise ValueError("Evento de auditoria sem identificador.")
    affected, resources, sites, recipients = _resource_dimensions(operation)
    kind = str(operation.get("kind") or "action").strip().lower()[:120]
    timestamp = float(event.get("ts") or time.time())
    if not math.isfinite(timestamp):
        timestamp = time.time()

    with _LOCK, _connect(target) as connection:
        connection.execute("BEGIN IMMEDIATE")
        duplicate = connection.execute(
            """
            SELECT * FROM audit_integrity_ledger
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        if duplicate is not None:
            connection.commit()
            return _row_public(duplicate)
        previous = connection.execute(
            """
            SELECT sequence, entry_hash
            FROM audit_integrity_ledger
            ORDER BY sequence DESC
            LIMIT 1
            """
        ).fetchone()
        sequence = int(previous["sequence"]) + 1 if previous else 1
        previous_hash = str(previous["entry_hash"]) if previous else GENESIS_HASH
        ledger_id = f"audit-{sequence}-{event_id}"
        payload = {
            "version": 1,
            "sequence": sequence,
            "id": ledger_id,
            "previous_hash": previous_hash,
            "ts": timestamp,
            "operation_id": operation_id,
            "event_id": event_id,
            "event_type": str(event.get("type") or "event")[:120],
            "kind": kind,
            "project_id": _project_id(operation),
            "resources": affected,
            "resource_terms": resources,
            "sites": sites,
            "recipients": recipients,
            "message": _bounded_text(event.get("message"), 2_000),
            "data": _safe_value(event.get("data") or {}),
        }
        payload_json = _canonical(payload)
        digest = _entry_hash(previous_hash, payload_json)
        connection.execute(
            """
            INSERT INTO audit_integrity_ledger (
                sequence, id, previous_hash, entry_hash, payload_json, ts,
                operation_id, event_id, event_type, kind, project_id,
                resource_text, site_text, recipient_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sequence,
                ledger_id,
                previous_hash,
                digest,
                payload_json,
                timestamp,
                operation_id,
                event_id,
                payload["event_type"],
                kind,
                payload["project_id"],
                "\n".join(resources).casefold(),
                "\n".join(sites).casefold(),
                "\n".join(recipients).casefold(),
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM audit_integrity_ledger WHERE sequence = ?",
            (sequence,),
        ).fetchone()
    assert row is not None
    return _row_public(row)


def _finite_timestamp(value: float | str | None, label: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                f"{label} precisa ser timestamp ou data ISO 8601."
            ) from exc
        number = parsed.timestamp()
    if not math.isfinite(number):
        raise ValueError(f"{label} precisa ser um timestamp finito.")
    return number


def _like(value: str) -> str:
    return (
        str(value or "")
        .casefold()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def search(
    *,
    since: float | str | None = None,
    until: float | str | None = None,
    kind: str | None = None,
    project_id: str | None = None,
    resource: str | None = None,
    site: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
    limit: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    target = db_path or _DB_PATH
    _init_db(target)
    since = _finite_timestamp(since, "since")
    until = _finite_timestamp(until, "until")
    if since is not None and until is not None and since > until:
        raise ValueError("O início do período precisa ser anterior ao fim.")
    clauses: list[str] = []
    values: list[Any] = []
    if since is not None:
        clauses.append("ts >= ?")
        values.append(since)
    if until is not None:
        clauses.append("ts <= ?")
        values.append(until)
    if kind:
        clauses.append("kind = ?")
        values.append(str(kind).strip().lower()[:120])
    if project_id:
        clauses.append("project_id = ?")
        values.append(str(project_id).strip()[:240])
    for column, value in (
        ("resource_text", resource),
        ("site_text", site),
        ("recipient_text", recipient),
    ):
        if value:
            clauses.append(f"{column} LIKE ? ESCAPE '\\'")
            values.append(f"%{_like(value)}%")
    if query:
        needle = f"%{_like(query)}%"
        clauses.append(
            "("
            "kind LIKE ? ESCAPE '\\' OR "
            "event_type LIKE ? ESCAPE '\\' OR "
            "COALESCE(project_id, '') LIKE ? ESCAPE '\\' OR "
            "resource_text LIKE ? ESCAPE '\\' OR "
            "site_text LIKE ? ESCAPE '\\' OR "
            "recipient_text LIKE ? ESCAPE '\\' OR "
            "payload_json LIKE ? ESCAPE '\\'"
            ")"
        )
        values.extend([needle] * 7)
    safe_limit = max(1, min(int(limit), 1_000))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _LOCK, _connect(target) as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM audit_integrity_ledger
            {where}
            ORDER BY ts DESC, sequence DESC
            LIMIT ?
            """,
            [*values, safe_limit + 1],
        ).fetchall()
    truncated = len(rows) > safe_limit
    entries = [_row_public(row) for row in rows[:safe_limit]]
    return {
        "format": "aether-audit-search-v1",
        "filters": {
            "since": since,
            "until": until,
            "kind": kind,
            "project_id": project_id,
            "resource": resource,
            "site": site,
            "recipient": recipient,
            "query": query,
        },
        "entries": entries,
        "count": len(entries),
        "limit": safe_limit,
        "truncated": truncated,
        "redacted": True,
    }


def verify_chain(*, db_path: Path | None = None) -> dict[str, Any]:
    target = db_path or _DB_PATH
    _init_db(target)
    with _LOCK, _connect(target) as connection:
        rows = connection.execute(
            "SELECT * FROM audit_integrity_ledger ORDER BY sequence"
        ).fetchall()
    expected_previous = GENESIS_HASH
    expected_sequence = 1
    for row in rows:
        reasons: list[str] = []
        sequence = int(row["sequence"])
        if sequence != expected_sequence:
            reasons.append("sequência não contígua")
        if row["previous_hash"] != expected_previous:
            reasons.append("hash anterior divergente")
        calculated = _entry_hash(str(row["previous_hash"]), row["payload_json"])
        if calculated != row["entry_hash"]:
            reasons.append("conteúdo ou hash do evento divergente")
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
            reasons.append("payload inválido")
        comparisons = {
            "sequence": sequence,
            "id": row["id"],
            "previous_hash": row["previous_hash"],
            "ts": float(row["ts"]),
            "operation_id": row["operation_id"],
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "kind": row["kind"],
            "project_id": row["project_id"],
        }
        if any(payload.get(key) != value for key, value in comparisons.items()):
            reasons.append("índices de pesquisa divergem do payload assinado")
        derived_search = {
            "resource_text": "\n".join(
                str(item) for item in payload.get("resource_terms", [])
            ).casefold(),
            "site_text": "\n".join(
                str(item) for item in payload.get("sites", [])
            ).casefold(),
            "recipient_text": "\n".join(
                str(item) for item in payload.get("recipients", [])
            ).casefold(),
        }
        if any(
            str(row[column]) != expected
            for column, expected in derived_search.items()
        ):
            reasons.append("índices textuais divergem do payload assinado")
        if reasons:
            return {
                "valid": False,
                "algorithm": "sha256",
                "entries_checked": expected_sequence - 1,
                "total_entries": len(rows),
                "first_invalid_sequence": sequence,
                "event_id": row["event_id"],
                "reasons": reasons,
                "tamper_evident": True,
            }
        expected_previous = str(row["entry_hash"])
        expected_sequence += 1
    return {
        "valid": True,
        "algorithm": "sha256",
        "entries_checked": len(rows),
        "total_entries": len(rows),
        "first_invalid_sequence": None,
        "reasons": [],
        "head_hash": expected_previous,
        "tamper_evident": True,
    }


def markdown_report(
    *,
    since: float | str | None = None,
    until: float | str | None = None,
    kind: str | None = None,
    project_id: str | None = None,
    resource: str | None = None,
    site: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
    limit: int = 200,
    db_path: Path | None = None,
) -> str:
    result = search(
        since=since,
        until=until,
        kind=kind,
        project_id=project_id,
        resource=resource,
        site=site,
        recipient=recipient,
        query=query,
        limit=limit,
        db_path=db_path,
    )
    integrity = verify_chain(db_path=db_path)

    def cell(value: Any) -> str:
        return _bounded_text(value, 300).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Relatório de auditoria do Aether",
        "",
        f"- Gerado em: {time.strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- Integridade da cadeia: {'válida' if integrity['valid'] else 'inválida'}",
        f"- Algoritmo: {integrity['algorithm']}",
        f"- Eventos encontrados: {result['count']}",
        "- Conteúdo: redigido e limitado a metadados de auditoria",
        "",
        "| Data | Tipo | Evento | Projeto | Recursos | Mudança | Sites | Destinatários |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in result["entries"]:
        lines.append(
            "| "
            + " | ".join([
                time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(float(entry["ts"])),
                ),
                cell(entry["kind"]),
                cell(entry["event_type"]),
                cell(entry.get("project_id") or "—"),
                cell(", ".join(
                    str(item.get("name") or item.get("path") or "")
                    for item in entry.get("resources", [])
                    if isinstance(item, dict)
                ) or "—"),
                cell(
                    (
                        f"{entry['state_change'].get('before', '—')} → "
                        f"{entry['state_change'].get('after', '—')}"
                    )
                    if entry.get("state_change")
                    else "—"
                ),
                cell(", ".join(entry.get("sites", [])) or "—"),
                cell(", ".join(entry.get("recipients", [])) or "—"),
            ])
            + " |"
        )
    if not result["entries"]:
        lines.append("| — | — | — | — | — | — | — | — |")
    lines.extend([
        "",
        "> A cadeia é resistente à detecção de alterações, não à exclusão do "
        "arquivo inteiro. Proteja backups e permissões do banco para maior garantia.",
        "",
    ])
    return "\n".join(lines)
