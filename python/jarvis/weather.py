from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from . import privacy_control
from .config import settings
from .redaction import redact_text

logger = logging.getLogger("jarvis.weather")


def _weather_api_key() -> str:
    """Use a dedicated weather credential; never reuse an LLM provider key."""
    # ``settings`` captured launch credentials before config scrubbed the
    # process environment.  The pop fallback keeps isolated tests/embedders
    # compatible without leaving a newly injected key available to children.
    return str(
        settings.weather_api_key
        or os.environ.pop("WEATHER_API_KEY", "")
        or os.environ.pop("OPENWEATHER_API_KEY", "")
    ).strip()


def _privacy_block() -> dict[str, Any] | None:
    decision = privacy_control.network_decision(
        "https://api.openweathermap.org",
        provider="openweather",
    )
    if decision["allowed"]:
        return None
    return {
        "ok": False,
        "blocked": True,
        "privacy": decision,
        "error": "Clima externo bloqueado pelo perfil 100% local.",
    }


async def get_weather(city: str = "") -> dict[str, Any]:
    if blocked := _privacy_block():
        return blocked
    api_key = _weather_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "OpenWeather API key not configured.",
            "hint": "Add WEATHER_API_KEY=your_key to .env"
        }
    location = str(city or "").strip()
    if len(location) > 160:
        return {"ok": False, "error": "O nome da cidade é longo demais."}
    location = location or "São Paulo,BR"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": location, "appid": api_key, "units": "metric", "lang": "pt_br"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "ok": True,
            "city": data.get("name", location),
            "country": data.get("sys", {}).get("country", ""),
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "description": data["weather"][0]["description"],
            "icon": data["weather"][0]["icon"],
            "wind_speed": data["wind"]["speed"],
            "wind_direction": data.get("wind", {}).get("deg", 0),
        }
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            return {"ok": False, "error": "API key inválida. WEATHER_API_KEY incorreta ou não configurada."}
        if exc.response.status_code == 404:
            return {"ok": False, "error": f"Cidade '{location}' não encontrada."}
        return {"ok": False, "error": f"Erro ao buscar clima: {exc.response.status_code}"}
    except Exception as exc:
        return {"ok": False, "error": redact_text(exc)}


async def get_forecast(city: str = "", days: int = 3) -> dict[str, Any]:
    if blocked := _privacy_block():
        return blocked
    api_key = _weather_api_key()
    if not api_key:
        return {
            "ok": False,
            "error": "WEATHER_API_KEY not configured.",
            "hint": "Add WEATHER_API_KEY=your_key to .env",
        }
    location = str(city or "").strip()
    if len(location) > 160:
        return {"ok": False, "error": "O nome da cidade é longo demais."}
    location = location or "São Paulo,BR"
    days = max(1, min(int(days), 5))
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"q": location, "appid": api_key, "units": "metric", "lang": "pt_br", "cnt": days * 8},
            )
            resp.raise_for_status()
            data = resp.json()
        forecasts: list[dict[str, Any]] = []
        for item in data.get("list", []):
            forecasts.append({
                "datetime": item["dt_txt"],
                "temperature": item["main"]["temp"],
                "description": item["weather"][0]["description"],
                "humidity": item["main"]["humidity"],
                "wind_speed": item["wind"]["speed"],
            })
        return {
            "ok": True,
            "city": data.get("city", {}).get("name", location),
            "forecasts": forecasts[:days * 8],
        }
    except Exception as exc:
        return {"ok": False, "error": redact_text(exc)}
