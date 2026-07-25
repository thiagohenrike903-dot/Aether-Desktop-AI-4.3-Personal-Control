"""Guided, secret-free connection catalogue and connection tests."""
from __future__ import annotations

import shutil
import time
from typing import Any

from . import model_profiles, project_library
from .config import settings
from .llm_providers import get_provider


def _profile_state(profile: dict[str, Any]) -> dict[str, Any]:
    provider = get_provider(profile)
    reason: str | None = None
    if not profile.get("enabled"):
        reason = "Perfil desativado."
    elif not profile.get("model"):
        reason = "Nenhum modelo foi configurado."
    elif provider is None:
        reason = "A credencial ou o provedor ainda não está configurado."
    return {
        "id": profile["id"],
        "name": profile["name"],
        "provider": profile["provider"],
        "model": profile["model"] or None,
        "base_url": profile.get("base_url"),
        "offline": bool(profile.get("offline")),
        "enabled": bool(profile.get("enabled")),
        "configured": provider is not None,
        "status": "ready" if provider is not None else "unavailable",
        "reason": reason,
    }


def offline_capabilities() -> list[dict[str, Any]]:
    documents = project_library.capabilities()
    semantic = bool(documents["semantic_index"]["available"])
    return [
        {"id": "projects", "name": "Projetos e conversas", "available": True},
        {"id": "memory", "name": "Memórias locais", "available": True},
        {"id": "documents", "name": "Leitura e busca lexical", "available": True},
        {
            "id": "ocr",
            "name": "OCR",
            "available": bool(documents["ocr"]["available"]),
            "reason": None if documents["ocr"]["available"] else "Tesseract não instalado.",
        },
        {
            "id": "semantic_index",
            "name": "Índice semântico local",
            "available": semantic,
            "reason": None if semantic else "Dependências locais opcionais não instaladas.",
        },
        {
            "id": "local_model",
            "name": "Chat com modelo local",
            "available": any(
                profile["offline"] and profile["configured"]
                for profile in map(_profile_state, model_profiles.list_profiles())
            ),
        },
        {"id": "web_research", "name": "Pesquisa web", "available": False},
        {"id": "cloud_models", "name": "Modelos externos", "available": False},
    ]


def overview() -> dict[str, Any]:
    profiles = [_profile_state(item) for item in model_profiles.list_profiles()]
    legacy = {
        "google_client": (settings.data_dir / "gmail_credentials.json").is_file(),
        "gmail_token": (settings.data_dir / "gmail_token.json").is_file(),
        "calendar_token": (settings.data_dir / "calendar_token.json").is_file(),
    }
    secure_storage = bool(settings.vault_enforced)

    def secret_storage(configured: bool) -> str:
        if not configured:
            return "unconfigured"
        return (
            "operating_system_vault"
            if secure_storage
            else "environment_configuration"
        )

    integrations = [
        {
            "id": "gmail",
            "name": "Gmail",
            "configured": bool(settings.gmail_oauth_token_json or legacy["gmail_token"]),
            "storage": (
                "operating_system_vault"
                if settings.gmail_oauth_token_json and secure_storage
                else "environment_configuration"
                if settings.gmail_oauth_token_json
                else ("legacy_file" if legacy["gmail_token"] else "unconfigured")
            ),
            "needs_migration": bool(
                (legacy["gmail_token"] or legacy["google_client"])
                and not settings.gmail_oauth_token_json
            ),
        },
        {
            "id": "google_calendar",
            "name": "Google Calendar",
            "configured": bool(
                settings.calendar_oauth_token_json or legacy["calendar_token"]
            ),
            "storage": (
                "operating_system_vault"
                if settings.calendar_oauth_token_json and secure_storage
                else "environment_configuration"
                if settings.calendar_oauth_token_json
                else ("legacy_file" if legacy["calendar_token"] else "unconfigured")
            ),
            "needs_migration": bool(
                (legacy["calendar_token"] or legacy["google_client"])
                and not settings.calendar_oauth_token_json
            ),
        },
        {
            "id": "weather",
            "name": "Clima",
            "configured": bool(settings.weather_api_key),
            "storage": secret_storage(bool(settings.weather_api_key)),
            "needs_migration": False,
        },
        {
            "id": "voice",
            "name": "ElevenLabs",
            "configured": bool(settings.elevenlabs_api_key),
            "storage": secret_storage(bool(settings.elevenlabs_api_key)),
            "needs_migration": False,
        },
    ]
    return {
        "ok": True,
        "profiles": profiles,
        "integrations": integrations,
        "active_profile_id": model_profiles.get_active_profile_id(),
        "offline_capabilities": offline_capabilities(),
        "system_dependencies": {
            "python": True,
            "tesseract": bool(shutil.which("tesseract")),
        },
        "credential_storage": {
            "location": "operating_system_vault",
            "sent_to_renderer": False,
            "sent_to_model": False,
            "legacy_files_detected": any(legacy.values()),
            "migration_required": any(
                item["needs_migration"] for item in integrations
            ),
        },
    }


async def test(profile_id: str) -> dict[str, Any]:
    profile = model_profiles.get_profile(profile_id)
    if profile is None:
        raise KeyError(profile_id)
    provider = get_provider(profile)
    if provider is None:
        return {
            "ok": False,
            "profile_id": profile_id,
            "status": "unavailable",
            "error": (
                "O perfil não possui todas as configurações necessárias. "
                "Revise modelo, endpoint e credencial."
            ),
            "latency_ms": 0,
        }
    started = time.perf_counter()
    try:
        reply = await provider.respond(
            "Teste de conectividade do Aether. Responda somente OK.",
            [{"role": "user", "parts": [{"text": "OK"}]}],
            temperature=0,
            max_tokens=4,
        )
    except Exception:
        reply = None
    latency = round((time.perf_counter() - started) * 1_000, 2)
    return {
        "ok": bool(reply),
        "profile_id": profile_id,
        "status": "ready" if reply else "failed",
        "latency_ms": latency,
        "error": None if reply else (
            "A conexão não respondeu. Verifique credencial, modelo, rede e endpoint."
        ),
        "detail": (
            "O provedor respondeu ao teste mínimo."
            if reply
            else "Nenhum conteúdo sensível do erro foi preservado."
        ),
    }
