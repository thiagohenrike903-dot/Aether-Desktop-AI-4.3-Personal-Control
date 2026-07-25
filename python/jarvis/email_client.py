from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from . import privacy_control
from .config import settings

logger = logging.getLogger("jarvis.email")

_GOOGLE_CREDENTIALS_FILE = settings.data_dir / "gmail_credentials.json"
_TOKEN_FILE = settings.data_dir / "gmail_token.json"
_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _privacy_error() -> dict[str, Any] | None:
    decision = privacy_control.network_decision(
        "https://gmail.googleapis.com",
        provider="gmail",
    )
    if decision["allowed"]:
        return None
    return {
        "ok": False,
        "blocked": True,
        "error": "Gmail bloqueado pelo perfil 100% local.",
        "privacy": decision,
    }


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


def _get_gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    secure_token = settings.gmail_oauth_token_json
    secure_client = settings.google_client_credentials_json
    using_vault_material = bool(secure_token or secure_client)
    if secure_token:
        try:
            token_payload = _vault_json_object(secure_token, "O token do Gmail")
            creds = Credentials.from_authorized_user_info(token_payload, _SCOPES)
        except (ValueError, TypeError, KeyError):
            raise RuntimeError(
                "O token do Gmail guardado no cofre é inválido."
            ) from None
    elif (
        not settings.vault_enforced
        and _TOKEN_FILE.exists()
        and _stored_token_has_scopes(_TOKEN_FILE, _SCOPES)
    ):
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)
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
                    "Credencial Google para Gmail não autorizada no cofre."
                )
            else:
                raise RuntimeError(
                    "Credenciais do Gmail não configuradas. Use a Central de "
                    "Conexões e o cofre do sistema."
                )
            creds = flow.run_local_server(port=0)
        if not settings.vault_enforced and not using_vault_material:
            # Compatibilidade explícita com instalações antigas. Novas
            # configurações feitas pela Central de Conexões permanecem em
            # memória/cofre e não criam um token no disco.
            _write_token(_TOKEN_FILE, creds.to_json())
    return build("gmail", "v1", credentials=creds)


async def list_emails(max_results: int = 10, query: str = "") -> list[dict[str, Any]]:
    if blocked := _privacy_error():
        return [blocked]
    try:
        service = await asyncio.to_thread(_get_gmail_service)
        results = await asyncio.to_thread(
            lambda: service.users().messages().list(
                userId="me", maxResults=max_results, q=query
            ).execute()
        )
        messages = results.get("messages", [])
        emails: list[dict[str, Any]] = []
        for msg in messages[:max_results]:
            meta = await asyncio.to_thread(
                lambda: service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"]
                ).execute()
            )
            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": meta.get("snippet", ""),
            })
        return emails
    except ImportError:
        return [{"error": "google-api-python-client not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"}]
    except Exception as exc:
        logger.warning("Failed to list emails: %s", exc)
        return [{"error": str(exc)}]


async def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    import base64
    from email.message import EmailMessage

    if blocked := _privacy_error():
        return blocked
    try:
        service = await asyncio.to_thread(_get_gmail_service)
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body_payload = {"raw": encoded}

        sent = await asyncio.to_thread(
            lambda: service.users().messages().send(userId="me", body=body_payload).execute()
        )
        return {"ok": True, "id": sent.get("id", ""), "to": to, "subject": subject}
    except ImportError:
        return {"ok": False, "error": "google-api-python-client not installed."}
    except Exception as exc:
        logger.warning("Failed to send email: %s", exc)
        return {"ok": False, "error": str(exc)}


async def search_emails(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    return await list_emails(max_results=max_results, query=query)


def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None
