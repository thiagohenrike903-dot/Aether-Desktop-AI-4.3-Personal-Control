"""Persistent privacy mode and metadata-only data-flow map.

``standard`` permits validated HTTP(S) destinations. ``local_only`` permits
only endpoints whose host is demonstrably loopback.  The historic ``offline``
checkbox is deliberately ignored: a profile is local because of where it
connects, not because of what its label claims.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import settings

VALID_MODES = frozenset({"standard", "local_only"})
_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS privacy_state (
    singleton   INTEGER PRIMARY KEY CHECK (singleton = 1),
    mode        TEXT NOT NULL CHECK (mode IN ('standard', 'local_only')),
    updated_at  REAL NOT NULL
);
INSERT OR IGNORE INTO privacy_state (singleton, mode, updated_at)
VALUES (1, 'standard', 0);

CREATE TABLE IF NOT EXISTS conversation_privacy (
    conversation_id  TEXT PRIMARY KEY,
    mode             TEXT NOT NULL CHECK (mode IN ('standard', 'local_only')),
    updated_at       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS privacy_flows (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT,
    request_id       TEXT,
    provider         TEXT NOT NULL,
    endpoint         TEXT NOT NULL,
    domain           TEXT NOT NULL,
    destination      TEXT NOT NULL,
    categories_json  TEXT NOT NULL,
    blocked          INTEGER NOT NULL,
    reason           TEXT NOT NULL,
    ts               REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_privacy_flows_conversation
ON privacy_flows(conversation_id, ts DESC);
CREATE INDEX IF NOT EXISTS ix_privacy_flows_request
ON privacy_flows(request_id, ts DESC);
"""

_PROVIDER_ENDPOINTS = {
    "gemini": "https://generativelanguage.googleapis.com",
    "glm": "https://open.bigmodel.cn",
    "qwen_api": "https://dashscope.aliyuncs.com",
    "openai": "https://api.openai.com",
    "ollama": "http://localhost:11434",
    "qwen": "http://localhost:11434",
}


class PrivacyBlockedError(RuntimeError):
    """Network request rejected by the effective privacy mode."""

    def __init__(self, message: str, decision: dict[str, Any]) -> None:
        super().__init__(message)
        self.decision = decision


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
        raise ValueError("Modo de privacidade inválido. Use standard ou local_only.")
    return value


def get_state() -> dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT mode, updated_at FROM privacy_state WHERE singleton = 1"
        ).fetchone()
    if row is None:
        _init_db()
        return {
            "mode": "standard",
            "updated_at": 0.0,
            "integrity_fallback": False,
        }
    raw = str(row["mode"] or "").strip().lower()
    fallback = raw not in VALID_MODES
    return {
        "mode": "local_only" if fallback else raw,
        "updated_at": float(row["updated_at"]),
        "integrity_fallback": fallback,
    }


def get_mode() -> str:
    return str(get_state()["mode"])


def set_mode(mode: str) -> dict[str, Any]:
    value = normalize_mode(mode)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO privacy_state (singleton, mode, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(singleton)
            DO UPDATE SET mode = excluded.mode, updated_at = excluded.updated_at
            """,
            (value, now),
        )
        connection.commit()
    return {"mode": value, "updated_at": now, "integrity_fallback": False}


def _conversation_id(value: str) -> str:
    identifier = str(value or "").strip()
    if not identifier or len(identifier) > 240:
        raise ValueError("Identificador de conversa inválido.")
    return identifier


def set_conversation_mode(conversation_id: str, mode: str) -> dict[str, Any]:
    identifier = _conversation_id(conversation_id)
    value = normalize_mode(mode)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO conversation_privacy
                (conversation_id, mode, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(conversation_id)
            DO UPDATE SET mode = excluded.mode, updated_at = excluded.updated_at
            """,
            (identifier, value, now),
        )
        connection.commit()
    return {
        "conversation_id": identifier,
        "mode": value,
        "updated_at": now,
    }


def get_conversation_mode(conversation_id: str) -> dict[str, Any] | None:
    identifier = _conversation_id(conversation_id)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT conversation_id, mode, updated_at
            FROM conversation_privacy
            WHERE conversation_id = ?
            """,
            (identifier,),
        ).fetchone()
    if row is None:
        return None
    raw = str(row["mode"] or "").strip().lower()
    fallback = raw not in VALID_MODES
    return {
        "conversation_id": str(row["conversation_id"]),
        "mode": "local_only" if fallback else raw,
        "updated_at": float(row["updated_at"]),
        "integrity_fallback": fallback,
    }


def delete_conversation_mode(conversation_id: str) -> bool:
    identifier = _conversation_id(conversation_id)
    with _LOCK, _connect() as connection:
        result = connection.execute(
            "DELETE FROM conversation_privacy WHERE conversation_id = ?",
            (identifier,),
        )
        connection.commit()
    return result.rowcount > 0


def effective_mode(conversation_id: str | None = None) -> dict[str, Any]:
    global_state = get_state()
    override = (
        get_conversation_mode(conversation_id)
        if conversation_id
        else None
    )
    return {
        "mode": str((override or global_state)["mode"]),
        "global_mode": str(global_state["mode"]),
        "conversation_id": conversation_id,
        "conversation_mode": str(override["mode"]) if override else None,
        "integrity_fallback": bool(global_state["integrity_fallback"])
        or bool((override or {}).get("integrity_fallback")),
    }


def _loopback_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return bool(address.ipv4_mapped.is_loopback)
    return bool(address.is_loopback)


def _validated_loopback_host(hostname: str, port: int | None) -> tuple[bool, list[str]]:
    host = str(hostname or "").strip().casefold().rstrip(".")
    if _loopback_ip(host):
        return True, [host]
    if host != "localhost":
        return False, []
    try:
        answers = socket.getaddrinfo(
            host,
            port or 80,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return False, []
    addresses = sorted({str(answer[4][0]) for answer in answers if answer[4]})
    return bool(addresses) and all(_loopback_ip(item) for item in addresses), addresses


def classify_endpoint(endpoint: str) -> dict[str, Any]:
    """Classify one URL from its validated network destination."""
    raw = str(endpoint or "").strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        parsed = urlsplit("")
        port = None
    scheme = parsed.scheme.casefold()
    hostname = parsed.hostname or ""
    valid = (
        scheme in {"http", "https"}
        and bool(hostname)
        and parsed.username is None
        and parsed.password is None
    )
    if not valid:
        return {
            "endpoint": raw,
            "scheme": scheme or None,
            "domain": hostname,
            "valid": False,
            "local": False,
            "destination": "invalid",
            "validated_ips": [],
            "reason": "O endpoint precisa ser uma URL HTTP(S) sem credenciais embutidas.",
        }
    local, addresses = _validated_loopback_host(hostname, port)
    return {
        "endpoint": f"{scheme}://{parsed.netloc}",
        "scheme": scheme,
        "domain": hostname.casefold(),
        "valid": True,
        "local": local,
        "destination": "local" if local else "external",
        "validated_ips": addresses,
        "reason": (
            "O host foi validado como loopback."
            if local
            else "O host não é um endpoint loopback validado."
        ),
    }


def provider_endpoint(
    provider: str,
    base_url: str | None = None,
) -> str:
    normalized = str(provider or "").strip().lower()
    # Gemini and GLM clients use fixed vendor endpoints; a profile's decorative
    # base_url must not make an external request appear local.
    if normalized in {"gemini", "glm"}:
        return _PROVIDER_ENDPOINTS[normalized]
    value = str(base_url or "").strip()
    if value:
        return value
    if normalized in {"ollama", "qwen"}:
        return settings.ollama_base_url
    if normalized == "openai" and settings.llm_base_url:
        return settings.llm_base_url
    return _PROVIDER_ENDPOINTS.get(normalized, "")


def profile_destination(profile: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(profile or {})
    provider = str(item.get("provider") or settings.llm_provider or "").strip().lower()
    endpoint = provider_endpoint(
        provider,
        str(item.get("base_url") or "").strip() or None,
    )
    classification = classify_endpoint(endpoint)
    return {
        "profile_id": item.get("id"),
        "provider": provider or "unconfigured",
        "model": str(item.get("model") or "")[:240],
        "available": bool(item.get("available", item.get("enabled", True))),
        **classification,
    }


def network_decision(
    endpoint: str,
    *,
    provider: str = "network",
    conversation_id: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    effective = effective_mode(conversation_id)
    selected_mode = normalize_mode(mode) if mode is not None else str(effective["mode"])
    classification = classify_endpoint(endpoint)
    if not classification["valid"]:
        allowed = False
        reason = str(classification["reason"])
    elif selected_mode == "local_only" and not classification["local"]:
        allowed = False
        reason = "O perfil 100% local bloqueia qualquer destino que não seja loopback."
    else:
        allowed = True
        reason = (
            "Destino loopback permitido."
            if classification["local"]
            else "Destino externo permitido pelo modo padrão."
        )
    return {
        **classification,
        **effective,
        "mode": selected_mode,
        "provider": str(provider or "network")[:120],
        "allowed": allowed,
        "blocked": not allowed,
        "reason": reason,
    }


def _clean_categories(categories: list[str] | tuple[str, ...] | None) -> list[str]:
    return list(dict.fromkeys(
        str(item).strip()[:120]
        for item in (categories or [])
        if str(item).strip()
    ))[:40]


def record_flow(
    *,
    endpoint: str,
    provider: str,
    categories: list[str] | tuple[str, ...] | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = decision or network_decision(
        endpoint,
        provider=provider,
        conversation_id=conversation_id,
    )
    flow_id = str(uuid.uuid4())
    now = time.time()
    identifier = str(conversation_id or "").strip()[:240] or None
    safe_categories = _clean_categories(categories)
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO privacy_flows (
                id, conversation_id, request_id, provider, endpoint, domain,
                destination, categories_json, blocked, reason, ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flow_id,
                identifier,
                str(request_id or "").strip()[:240] or None,
                str(provider or "network")[:120],
                str(verdict.get("endpoint") or "")[:500],
                str(verdict.get("domain") or "")[:240],
                str(verdict.get("destination") or "invalid")[:40],
                json.dumps(safe_categories, ensure_ascii=False),
                int(bool(verdict.get("blocked"))),
                str(verdict.get("reason") or "")[:500],
                now,
            ),
        )
        connection.commit()
    return {
        "id": flow_id,
        "conversation_id": identifier,
        "request_id": str(request_id or "").strip()[:240] or None,
        "provider": str(provider or "network")[:120],
        "endpoint": str(verdict.get("endpoint") or "")[:500],
        "domain": str(verdict.get("domain") or "")[:240],
        "destination": str(verdict.get("destination") or "invalid"),
        "categories": safe_categories,
        "blocked": bool(verdict.get("blocked")),
        "reason": str(verdict.get("reason") or ""),
        "ts": now,
    }


def enforce_network(
    endpoint: str,
    *,
    provider: str = "network",
    categories: list[str] | tuple[str, ...] | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    record: bool = True,
) -> dict[str, Any]:
    decision = network_decision(
        endpoint,
        provider=provider,
        conversation_id=conversation_id,
    )
    if record and conversation_id:
        record_flow(
            endpoint=endpoint,
            provider=provider,
            categories=categories,
            conversation_id=conversation_id,
            request_id=request_id,
            decision=decision,
        )
    if decision["blocked"]:
        raise PrivacyBlockedError(str(decision["reason"]), decision)
    return decision


def list_flows(
    conversation_id: str | None = None,
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    identifier = _conversation_id(conversation_id) if conversation_id else None
    safe_limit = max(1, min(int(limit), 1_000))
    with _LOCK, _connect() as connection:
        if identifier:
            rows = connection.execute(
                """
                SELECT * FROM privacy_flows
                WHERE conversation_id = ?
                ORDER BY ts DESC, rowid DESC
                LIMIT ?
                """,
                (identifier, safe_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM privacy_flows
                ORDER BY ts DESC, rowid DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        try:
            categories = json.loads(row["categories_json"])
        except (json.JSONDecodeError, TypeError):
            categories = []
        output.append({
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "request_id": row["request_id"],
            "provider": row["provider"],
            "endpoint": row["endpoint"],
            "domain": row["domain"],
            "destination": row["destination"],
            "categories": categories if isinstance(categories, list) else [],
            "blocked": bool(row["blocked"]),
            "reason": row["reason"],
            "ts": row["ts"],
        })
    return output


def privacy_map(
    conversation_id: str | None = None,
    *,
    limit: int = 200,
) -> dict[str, Any]:
    identifier = _conversation_id(conversation_id) if conversation_id else None
    flows = list_flows(identifier, limit=limit)
    categories = sorted({
        str(category)
        for flow in flows
        for category in flow["categories"]
    })
    return {
        **effective_mode(identifier),
        "conversation_id": identifier,
        "flows": flows,
        "flow_count": len(flows),
        "local_count": sum(flow["destination"] == "local" for flow in flows),
        "external_count": sum(flow["destination"] == "external" for flow in flows),
        "blocked_count": sum(flow["blocked"] for flow in flows),
        "outbound_categories": categories,
        "metadata_only": True,
    }
