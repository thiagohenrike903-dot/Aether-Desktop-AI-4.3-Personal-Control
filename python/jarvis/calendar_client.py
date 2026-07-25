from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import privacy_control
from .config import settings

logger = logging.getLogger("jarvis.calendar")

_GOOGLE_CREDENTIALS_FILE = settings.data_dir / "gmail_credentials.json"
_TOKEN_FILE = settings.data_dir / "calendar_token.json"
_LEGACY_TOKEN_FILE = settings.data_dir / "gmail_token.json"
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _privacy_error() -> dict[str, Any] | None:
    decision = privacy_control.network_decision(
        "https://www.googleapis.com/calendar/v3",
        provider="google_calendar",
    )
    if decision["allowed"]:
        return None
    return {
        "ok": False,
        "blocked": True,
        "error": "Google Calendar bloqueado pelo perfil 100% local.",
        "privacy": decision,
    }


def _resolve_timezone(timezone_name: str | None = None) -> str:
    """Resolve an IANA timezone without silently assuming a specific country."""
    if timezone_name:
        candidate = timezone_name.strip()
        try:
            ZoneInfo(candidate)
            return candidate
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Fuso horário IANA inválido: {candidate}") from exc

    candidates = [
        os.getenv("AETHER_TIMEZONE", "").strip(),
        os.getenv("TZ", "").strip(),
        str(getattr(datetime.datetime.now().astimezone().tzinfo, "key", "") or ""),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            ZoneInfo(candidate)
            return candidate
        except ZoneInfoNotFoundError:
            logger.warning("Ignoring invalid configured timezone: %s", candidate)
    return "UTC"


def _event_time(value: str, timezone_name: str) -> dict[str, str]:
    timestamp = value.strip()
    if not timestamp:
        raise ValueError("Horário do evento não pode ficar vazio.")
    try:
        parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "Use data e hora no formato ISO 8601, por exemplo 2026-07-24T14:30:00."
        ) from exc
    result = {"dateTime": timestamp}
    if parsed.tzinfo is None:
        result["timeZone"] = timezone_name
    return result


def _write_token(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _stored_token_has_scopes(path: Path, scopes: list[str]) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = set(payload.get("scopes") or [])
        return set(scopes).issubset(stored)
    except (OSError, ValueError, TypeError):
        return False


def _vault_json_object(raw: str, label: str) -> dict[str, Any]:
    """Decode an OAuth object without ever echoing secret material."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError(f"{label} guardado no cofre é inválido.") from None
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} guardado no cofre é inválido.")
    return payload


def _get_calendar_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token_source = None
    secure_token = settings.calendar_oauth_token_json
    secure_client = settings.google_client_credentials_json
    using_vault_material = bool(secure_token or secure_client)
    if secure_token:
        try:
            token_payload = _vault_json_object(
                secure_token,
                "O token do calendário",
            )
            creds = Credentials.from_authorized_user_info(token_payload, _SCOPES)
        except (ValueError, TypeError, KeyError):
            raise RuntimeError(
                "O token do calendário guardado no cofre é inválido."
            ) from None
    elif not settings.vault_enforced:
        for candidate in (_TOKEN_FILE, _LEGACY_TOKEN_FILE):
            if candidate.exists() and _stored_token_has_scopes(candidate, _SCOPES):
                token_source = candidate
                creds = Credentials.from_authorized_user_file(str(candidate), _SCOPES)
                break
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if secure_client:
                try:
                    client_payload = _vault_json_object(
                        secure_client,
                        "As credenciais Google",
                    )
                    flow = InstalledAppFlow.from_client_config(
                        client_payload,
                        _SCOPES,
                    )
                except (ValueError, TypeError, KeyError):
                    raise RuntimeError(
                        "As credenciais Google guardadas no cofre são inválidas."
                    ) from None
            elif (
                not settings.vault_enforced
                and _GOOGLE_CREDENTIALS_FILE.exists()
            ):
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(_GOOGLE_CREDENTIALS_FILE),
                    _SCOPES,
                )
            elif settings.vault_enforced:
                raise RuntimeError(
                    "Credencial Google para o calendário não autorizada no cofre."
                )
            else:
                raise RuntimeError(
                    "Credenciais do calendário não configuradas. Use a Central "
                    "de Conexões e o cofre do sistema."
                )
            creds = flow.run_local_server(port=0)
        if not settings.vault_enforced and not using_vault_material:
            _write_token(_TOKEN_FILE, creds.to_json())
    elif (
        token_source == _LEGACY_TOKEN_FILE
        and not settings.vault_enforced
        and not using_vault_material
    ):
        # One-time migration for users whose calendar token was written to the
        # shared Gmail token path by older versions.
        _write_token(_TOKEN_FILE, creds.to_json())
    return build("calendar", "v3", credentials=creds)


async def list_events(max_results: int = 10) -> dict[str, Any]:
    if blocked := _privacy_error():
        return blocked
    try:
        service = await asyncio.to_thread(_get_calendar_service)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = await asyncio.to_thread(
            lambda: service.events().list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        )
        events = events_result.get("items", [])
        result: list[dict[str, Any]] = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            result.append({
                "id": event["id"],
                "summary": event.get("summary", ""),
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "start": start,
                "end": end,
                "html_link": event.get("htmlLink", ""),
            })
        return {"ok": True, "events": result, "count": len(result)}
    except ImportError:
        return {"ok": False, "error": "google-api-python-client not installed."}
    except Exception as exc:
        logger.warning("Failed to list calendar events: %s", exc)
        return {"ok": False, "error": str(exc)}


async def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    timezone_name: str | None = None,
) -> dict[str, Any]:
    if blocked := _privacy_error():
        return blocked
    try:
        if not summary.strip():
            return {"ok": False, "error": "O título do evento é obrigatório."}
        resolved_timezone = _resolve_timezone(timezone_name)
        start = _event_time(start_time, resolved_timezone)
        end = _event_time(end_time, resolved_timezone)
        service = await asyncio.to_thread(_get_calendar_service)
        event = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": start,
            "end": end,
        }
        created = await asyncio.to_thread(
            lambda: service.events().insert(calendarId="primary", body=event).execute()
        )
        return {"ok": True, "event": {
            "id": created["id"],
            "summary": created.get("summary", ""),
            "html_link": created.get("htmlLink", ""),
        }}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except ImportError:
        return {"ok": False, "error": "google-api-python-client not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def delete_event(event_id: str) -> dict[str, Any]:
    if blocked := _privacy_error():
        return blocked
    try:
        service = await asyncio.to_thread(_get_calendar_service)
        await asyncio.to_thread(
            lambda: service.events().delete(calendarId="primary", eventId=event_id).execute()
        )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
