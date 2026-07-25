"""Launcher: ``python -m jarvis`` starts the Aether core on JARVIS_PORT."""
from __future__ import annotations

import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run(
        "jarvis.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
