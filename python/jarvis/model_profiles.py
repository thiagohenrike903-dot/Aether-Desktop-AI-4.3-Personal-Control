"""Configurable model profiles and local usage estimates.

Costs are explicitly estimates derived from user-configured per-token rates;
they are never presented as provider billing data.
"""
from __future__ import annotations

import json
import ipaddress
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import settings

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "control_center.sqlite3"
_PROTECTED_PROFILE_IDS = {"fast", "balanced", "deep", "vision", "offline"}
_CLOUD_PROVIDER_HOSTS = {
    "api.openai.com",
    "api.deepseek.com",
    "dashscope.aliyuncs.com",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_profiles (
    id                         TEXT PRIMARY KEY,
    name                       TEXT NOT NULL,
    description                TEXT NOT NULL,
    provider                   TEXT NOT NULL,
    model                      TEXT NOT NULL,
    base_url                   TEXT,
    temperature                REAL NOT NULL,
    max_tokens                 INTEGER NOT NULL,
    cost_limit_usd             REAL,
    cost_input_per_million     REAL NOT NULL DEFAULT 0,
    cost_output_per_million    REAL NOT NULL DEFAULT 0,
    fallback_profile_id        TEXT,
    vision                     INTEGER NOT NULL DEFAULT 0,
    offline                    INTEGER NOT NULL DEFAULT 0,
    enabled                    INTEGER NOT NULL DEFAULT 1,
    created_at                 REAL NOT NULL,
    updated_at                 REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS model_profile_state (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_usage (
    profile_id      TEXT PRIMARY KEY,
    requests        INTEGER NOT NULL DEFAULT 0,
    failures        INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_cost  REAL NOT NULL DEFAULT 0,
    updated_at      REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _configured_model() -> str:
    return str(settings.llm_model or settings.agent_orchestrator_model or "").strip()


def _defaults() -> list[dict[str, Any]]:
    provider = str(settings.llm_provider or "gemini").strip()
    model = _configured_model()
    offline_model = str(os.getenv("OLLAMA_MODEL") or "").strip()
    base = {
        "provider": provider,
        "model": model,
        "base_url": settings.llm_base_url,
        "cost_limit_usd": None,
        "cost_input_per_million": 0.0,
        "cost_output_per_million": 0.0,
        "fallback_profile_id": None,
        "offline": False,
        "enabled": bool(model),
    }
    return [
        {
            **base,
            "id": "fast",
            "name": "Rápido",
            "description": "Respostas curtas e menor limite de geração.",
            "temperature": 0.35,
            "max_tokens": 800,
            "vision": False,
        },
        {
            **base,
            "id": "balanced",
            "name": "Equilibrado",
            "description": "Perfil padrão para conversas e ferramentas.",
            "temperature": 0.45,
            "max_tokens": 1_400,
            "vision": False,
        },
        {
            **base,
            "id": "deep",
            "name": "Profundo",
            "description": "Mais espaço de saída para análises longas.",
            "temperature": 0.35,
            "max_tokens": 3_200,
            "vision": False,
        },
        {
            **base,
            "id": "vision",
            "name": "Visão",
            "description": "Perfil marcado para solicitações multimodais.",
            "temperature": 0.25,
            "max_tokens": 1_400,
            "vision": True,
        },
        {
            **base,
            "id": "offline",
            "name": "Offline",
            "description": "Usa Ollama local quando um OLLAMA_MODEL é configurado.",
            "provider": "ollama",
            "model": offline_model,
            "base_url": settings.ollama_base_url,
            "temperature": 0.4,
            "max_tokens": 1_400,
            "vision": False,
            "offline": True,
            "enabled": bool(offline_model),
        },
    ]


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        now = time.time()
        for profile in _defaults():
            connection.execute(
                """
                INSERT OR IGNORE INTO model_profiles (
                    id, name, description, provider, model, base_url,
                    temperature, max_tokens, cost_limit_usd,
                    cost_input_per_million, cost_output_per_million,
                    fallback_profile_id, vision, offline, enabled,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile["id"],
                    profile["name"],
                    profile["description"],
                    profile["provider"],
                    profile["model"],
                    profile["base_url"],
                    profile["temperature"],
                    profile["max_tokens"],
                    profile["cost_limit_usd"],
                    profile["cost_input_per_million"],
                    profile["cost_output_per_million"],
                    profile["fallback_profile_id"],
                    int(profile["vision"]),
                    int(profile["offline"]),
                    int(profile["enabled"]),
                    now,
                    now,
                ),
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO model_profile_state (key, value)
            VALUES ('active_profile_id', 'balanced')
            """
        )
        connection.commit()


_init_db()


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "provider": row["provider"],
        "model": row["model"],
        "base_url": row["base_url"],
        "temperature": row["temperature"],
        "max_tokens": row["max_tokens"],
        "cost_limit_usd": row["cost_limit_usd"],
        "cost_input_per_million": row["cost_input_per_million"],
        "cost_output_per_million": row["cost_output_per_million"],
        "fallback_profile_id": row["fallback_profile_id"],
        "vision": bool(row["vision"]),
        "offline": bool(row["offline"]),
        "enabled": bool(row["enabled"]),
        "available": bool(row["enabled"] and row["model"]),
        "protected": row["id"] in _PROTECTED_PROFILE_IDS,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_profiles() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM model_profiles ORDER BY rowid"
        ).fetchall()
    return [_public(row) for row in rows]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM model_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
    return _public(row) if row else None


def get_active_profile_id() -> str:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT value FROM model_profile_state WHERE key = 'active_profile_id'"
        ).fetchone()
    return str(row["value"] if row else "balanced")


def get_active_profile() -> dict[str, Any] | None:
    return get_profile(get_active_profile_id())


def set_active(profile_id: str) -> dict[str, Any]:
    profile = get_profile(profile_id)
    if profile is None:
        raise KeyError(profile_id)
    if not profile["enabled"] or not profile["model"]:
        raise ValueError("Este perfil não está disponível.")
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO model_profile_state (key, value)
            VALUES ('active_profile_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (profile_id,),
        )
        connection.commit()
    return profile


_EDITABLE_FIELDS = {
    "name",
    "description",
    "provider",
    "model",
    "base_url",
    "temperature",
    "max_tokens",
    "cost_limit_usd",
    "cost_input_per_million",
    "cost_output_per_million",
    "fallback_profile_id",
    "vision",
    "offline",
    "enabled",
}


def _validated_base_url(
    provider: str,
    value: Any,
    *,
    offline: bool = False,
) -> str | None:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("A URL base é inválida.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A URL base precisa usar HTTP ou HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("A URL base não pode conter credenciais.")
    host = parsed.hostname.casefold().rstrip(".")
    local_provider = provider in {"ollama", "qwen"} or offline
    if local_provider:
        try:
            address = ipaddress.ip_address(host)
            loopback = address.is_loopback
        except ValueError:
            loopback = host in {"localhost", "localhost.localdomain"}
        if not loopback:
            raise ValueError(
                "Perfis locais só podem usar um endpoint de loopback."
            )
        return raw
    if parsed.scheme != "https" or host not in _CLOUD_PROVIDER_HOSTS:
        raise ValueError(
            "O endpoint personalizado não está na lista de provedores públicos "
            "auditados. Use a URL oficial do provedor."
        )
    return raw


def _clean_changes(changes: dict[str, Any], *, profile_id: str) -> dict[str, Any]:
    clean = {key: value for key, value in changes.items() if key in _EDITABLE_FIELDS}
    provider = str(clean.get("provider") or "").strip()
    if provider and provider not in {
        "gemini",
        "glm",
        "qwen",
        "qwen_api",
        "openai",
        "ollama",
    }:
        raise ValueError("Provedor inválido.")
    if "temperature" in clean:
        clean["temperature"] = max(0.0, min(float(clean["temperature"]), 2.0))
    if "max_tokens" in clean:
        clean["max_tokens"] = max(64, min(int(clean["max_tokens"]), 64_000))
    for field in (
        "cost_limit_usd",
        "cost_input_per_million",
        "cost_output_per_million",
    ):
        if field in clean and clean[field] is not None:
            clean[field] = max(0.0, float(clean[field]))
    if clean.get("fallback_profile_id") == profile_id:
        raise ValueError("Um perfil não pode usar a si mesmo como fallback.")
    fallback_id = clean.get("fallback_profile_id")
    if fallback_id and get_profile(str(fallback_id)) is None:
        raise ValueError("Perfil de fallback não encontrado.")
    for boolean_field in ("vision", "offline", "enabled"):
        if boolean_field in clean:
            clean[boolean_field] = int(bool(clean[boolean_field]))
    if "base_url" in clean:
        effective_provider = str(
            clean.get("provider")
            or (get_profile(profile_id) or {}).get("provider")
            or ""
        )
        effective_offline = bool(
            clean.get(
                "offline",
                (get_profile(profile_id) or {}).get("offline", False),
            )
        )
        clean["base_url"] = _validated_base_url(
            effective_provider,
            clean["base_url"],
            offline=effective_offline,
        )
    for field, limit in (
        ("name", 160),
        ("description", 2_000),
        ("provider", 40),
        ("model", 240),
    ):
        if field in clean:
            clean[field] = str(clean[field] or "").strip()[:limit]
    return clean


def update_profile(profile_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    current = get_profile(profile_id)
    if current is None:
        raise KeyError(profile_id)
    clean = _clean_changes(changes, profile_id=profile_id)
    if not clean:
        return current
    assignments = ", ".join(f"{field} = ?" for field in clean)
    values = list(clean.values()) + [time.time(), profile_id]
    with _LOCK, _connect() as connection:
        connection.execute(
            f"UPDATE model_profiles SET {assignments}, updated_at = ? WHERE id = ?",
            values,
        )
        connection.commit()
    updated = get_profile(profile_id)
    assert updated is not None
    return updated


def create_profile(changes: dict[str, Any]) -> dict[str, Any]:
    """Create a reusable custom profile without mutating the five defaults."""
    profile_id = str(changes.get("id") or uuid.uuid4()).strip()[:120]
    if not profile_id or get_profile(profile_id) is not None:
        profile_id = str(uuid.uuid4())
    seed = {
        "name": changes.get("name") or "Novo perfil",
        "description": changes.get("description") or "",
        "provider": changes.get("provider") or settings.llm_provider or "gemini",
        "model": changes.get("model") or _configured_model(),
        "base_url": changes.get("base_url"),
        "temperature": changes.get("temperature", 0.45),
        "max_tokens": changes.get("max_tokens", 1_400),
        "cost_limit_usd": changes.get("cost_limit_usd"),
        "cost_input_per_million": changes.get("cost_input_per_million", 0.0),
        "cost_output_per_million": changes.get("cost_output_per_million", 0.0),
        "fallback_profile_id": changes.get("fallback_profile_id"),
        "vision": changes.get("vision", False),
        "offline": changes.get("offline", False),
        "enabled": changes.get("enabled", True),
    }
    clean = _clean_changes(seed, profile_id=profile_id)
    if not clean.get("name"):
        raise ValueError("O nome do perfil é obrigatório.")
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO model_profiles (
                id, name, description, provider, model, base_url,
                temperature, max_tokens, cost_limit_usd,
                cost_input_per_million, cost_output_per_million,
                fallback_profile_id, vision, offline, enabled,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                clean["name"],
                clean["description"],
                clean["provider"],
                clean["model"],
                clean.get("base_url"),
                clean["temperature"],
                clean["max_tokens"],
                clean.get("cost_limit_usd"),
                clean["cost_input_per_million"],
                clean["cost_output_per_million"],
                clean.get("fallback_profile_id"),
                clean["vision"],
                clean["offline"],
                clean["enabled"],
                now,
                now,
            ),
        )
        connection.commit()
    item = get_profile(profile_id)
    assert item is not None
    return item


def clone_profile(profile_id: str, *, name: str | None = None) -> dict[str, Any]:
    source = get_profile(profile_id)
    if source is None:
        raise KeyError(profile_id)
    return create_profile({
        **source,
        "id": None,
        "name": str(name or f"{source['name']} · cópia")[:160],
    })


def delete_profile(profile_id: str) -> bool:
    if profile_id in _PROTECTED_PROFILE_IDS:
        raise ValueError("Os cinco perfis padrão não podem ser excluídos.")
    if get_active_profile_id() == profile_id:
        raise ValueError("Altere o perfil ativo antes de excluir este perfil.")
    with _LOCK, _connect() as connection:
        connection.execute(
            "UPDATE model_profiles SET fallback_profile_id = NULL WHERE fallback_profile_id = ?",
            (profile_id,),
        )
        connection.execute("DELETE FROM model_usage WHERE profile_id = ?", (profile_id,))
        result = connection.execute(
            "DELETE FROM model_profiles WHERE id = ?", (profile_id,)
        )
        connection.commit()
    return result.rowcount > 0


def estimate_tokens(text: str) -> int:
    """Conservative language-agnostic estimate, clearly labelled as such."""
    return max(1, (len(str(text or "").encode("utf-8")) + 3) // 4)


def get_usage(profile_id: str | None = None) -> dict[str, Any]:
    profile_id = profile_id or get_active_profile_id()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM model_usage WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
    if not row:
        return {
            "profile_id": profile_id,
            "requests": 0,
            "failures": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "source": "local_estimate",
            "updated_at": None,
        }
    return {
        "profile_id": row["profile_id"],
        "requests": row["requests"],
        "failures": row["failures"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "estimated_cost_usd": round(row["estimated_cost"], 8),
        "source": "local_estimate",
        "updated_at": row["updated_at"],
    }


def all_usage() -> dict[str, dict[str, Any]]:
    return {profile["id"]: get_usage(profile["id"]) for profile in list_profiles()}


def limit_reached(profile: dict[str, Any]) -> bool:
    limit = profile.get("cost_limit_usd")
    if limit is None:
        return False
    return get_usage(profile["id"])["estimated_cost_usd"] >= float(limit)


def response_usage(
    profile: dict[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    failed: bool = False,
    duration_ms: float | None = None,
    first_token_ms: float | None = None,
) -> dict[str, Any]:
    """Return metrics for one response without mutating aggregate usage.

    Token counts and cost are local estimates unless a provider-specific
    adapter replaces them with measured values in the future. Keeping this
    payload separate from ``get_usage`` prevents the UI from presenting a
    profile's lifetime totals as if they belonged to the current response.
    """
    input_tokens = max(0, int(input_tokens))
    output_tokens = max(0, int(output_tokens))
    cost = (
        input_tokens * float(profile.get("cost_input_per_million") or 0.0)
        + output_tokens * float(profile.get("cost_output_per_million") or 0.0)
    ) / 1_000_000
    payload: dict[str, Any] = {
        "profile_id": str(profile.get("id") or ""),
        "scope": "response",
        "requests": 1,
        "failures": int(bool(failed)),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(cost, 8),
        "source": "local_estimate",
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(max(0.0, float(duration_ms)), 2)
    if first_token_ms is not None:
        payload["first_token_ms"] = round(max(0.0, float(first_token_ms)), 2)
    return payload


def record_usage(
    profile: dict[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    failed: bool = False,
) -> dict[str, Any]:
    input_tokens = max(0, int(input_tokens))
    output_tokens = max(0, int(output_tokens))
    cost = (
        input_tokens * float(profile.get("cost_input_per_million") or 0.0)
        + output_tokens * float(profile.get("cost_output_per_million") or 0.0)
    ) / 1_000_000
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO model_usage (
                profile_id, requests, failures, input_tokens,
                output_tokens, estimated_cost, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                requests = requests + 1,
                failures = failures + excluded.failures,
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                estimated_cost = estimated_cost + excluded.estimated_cost,
                updated_at = excluded.updated_at
            """,
            (
                profile["id"],
                int(failed),
                input_tokens,
                output_tokens,
                cost,
                now,
            ),
        )
        connection.commit()
    return get_usage(profile["id"])


def reset_usage(profile_id: str) -> dict[str, Any]:
    if get_profile(profile_id) is None:
        raise KeyError(profile_id)
    with _LOCK, _connect() as connection:
        connection.execute("DELETE FROM model_usage WHERE profile_id = ?", (profile_id,))
        connection.commit()
    return get_usage(profile_id)
