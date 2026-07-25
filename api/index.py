"""Vercel serverless entry point — wraps the Aether FastAPI app for Vercel.

This module adapts the desktop-native FastAPI application to run in Vercel's
serverless Python environment. Desktop-specific features (OS control, screenshots,
local filesystem, etc.) are gracefully unavailable; the API serves the LLM chat,
memory, projects, web search, and other cloud-compatible features.
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

os.environ.setdefault("VERCEL", "1")
os.environ.setdefault("JARVIS_HOST", "0.0.0.0")
os.environ.setdefault("JARVIS_PORT", "8765")
os.environ.setdefault("JARVIS_DATA_DIR", "/tmp/jarvis_data")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "python"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("aether.vercel")

try:
    from jarvis.app import app
except ImportError as exc:
    log.error("Failed to import Aether app: %s", exc)
    raise

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = app

app.routes = [r for r in app.routes if r.path != "/"]

_RENDERER_DIR = _PROJECT_ROOT / "renderer"
if _RENDERER_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_RENDERER_DIR), html=True), name="renderer")

@app.get("/api/status")
def api_status():
    from jarvis.app import APP_VERSION
    return {"service": "Aether Desktop AI", "version": APP_VERSION}

LOCAL_ORIGINS = {
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}

VERCEL_ORIGINS = set(
    origin.strip()
    for origin in os.environ.get("AETHER_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
) or {"https://*.vercel.app"}

ALLOWED_ORIGINS = sorted(LOCAL_ORIGINS | VERCEL_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Content-Type",
        "X-Aether-Token",
        "X-Aether-Confirmed",
        "X-Aether-Project-Id",
    ],
)
