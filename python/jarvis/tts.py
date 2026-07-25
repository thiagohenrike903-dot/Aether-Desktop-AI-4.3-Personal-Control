"""Text-to-speech for Aether via ElevenLabs or the local browser voice."""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, AsyncIterator

from . import privacy_control
from .config import settings

log = logging.getLogger("jarvis.tts")

# Module-level default voice; the FastAPI layer can override per-request.
DEFAULT_VOICE_ID = settings.elevenlabs_voice_id


def _has_key() -> bool:
    return bool(settings.elevenlabs_api_key)


def _external_voice_allowed() -> bool:
    return bool(privacy_control.network_decision(
        "https://api.elevenlabs.io",
        provider="elevenlabs",
    )["allowed"])


async def list_voices() -> list[dict[str, Any]]:
    """List available voices from ElevenLabs (if a key is configured)."""
    if not _has_key() or not _external_voice_allowed():
        return [{"voice_id": DEFAULT_VOICE_ID, "name": "Voz local do sistema"}]
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)  # type: ignore[arg-type]
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, client.voices.get_all)
        return [{"voice_id": v.voice_id, "name": v.name} for v in resp.voices]
    except Exception as exc:
        log.warning("Could not list ElevenLabs voices: %s", exc)
        return [{"voice_id": DEFAULT_VOICE_ID, "name": "Voz padrão Aether"}]


async def synthesise(text: str, voice_id: str | None = None,
                    model_id: str = "eleven_multilingual_v2") -> bytes:
    """Synthesise ``text`` to MP3 bytes.

    Empty bytes explicitly signal the renderer to use the operating system's
    speech engine. Returning synthetic silence would look like success while
    producing no audible result.
    """
    if not text.strip():
        return b""
    voice_id = voice_id or DEFAULT_VOICE_ID
    if not _has_key() or not _external_voice_allowed():
        # Returning no bytes tells the renderer to use Windows/Chromium's
        # built-in SpeechSynthesis voice. A silent MP3 looked successful but
        # produced no audible response.
        return b""

    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)  # type: ignore[arg-type]

        def _do() -> bytes:
            audio = client.generate(
                text=text,
                voice=voice_id,
                model=model_id,
                stream=False,
                output_format="mp3_44100_128",
            )
            if isinstance(audio, (bytes, bytearray)):
                return bytes(audio)
            # Some clients return an iterator of chunks
            buf = io.BytesIO()
            for chunk in audio:
                if chunk:
                    buf.write(chunk)
            return buf.getvalue()

        return await asyncio.to_thread(_do)
    except Exception as exc:
        log.warning("TTS failed (%s). Requesting local speech fallback.", exc)
        return b""


async def synthesise_stream(text: str, voice_id: str | None = None,
                            model_id: str = "eleven_multilingual_v2") -> AsyncIterator[bytes]:
    voice_id = voice_id or DEFAULT_VOICE_ID
    if not _has_key() or not _external_voice_allowed():
        return
    try:
        from elevenlabs.client import ElevenLabs  # type: ignore
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)  # type: ignore[arg-type]
        # The SDK returns a sync iterator; pump it in a thread.
        def _iter():
            return client.generate(
                text=text,
                voice=voice_id,
                model=model_id,
                stream=True,
                output_format="mp3_44100_128",
            )

        stream = await asyncio.to_thread(_iter)
        loop = asyncio.get_running_loop()
        while True:
            chunk = await loop.run_in_executor(None, next, stream, None)
            if chunk is None:
                break
            yield chunk
    except Exception as exc:
        log.warning("TTS stream failed: %s", exc)
        return
