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
from fastapi.responses import FileResponse, JSONResponse

app = app

app.routes = [r for r in app.routes if getattr(r, "path", None) != "/"]

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

_RENDERER_DIR = _PROJECT_ROOT / "renderer"


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
def serve_static(path: str):
    target = _RENDERER_DIR / (path or "index.html")
    if target.is_dir():
        target = target / "index.html"
    if target.is_file():
        return FileResponse(str(target))
    return JSONResponse({"ok": False, "detail": "Not found"}, status_code=404)
