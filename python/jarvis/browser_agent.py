"""Fail-closed browser automation for Aether 4.1.

Playwright resolves and connects inside Chromium, outside the pinned HTTP
transport used by professional research.  Request interception alone cannot
close the DNS-rebinding gap between validation and Chromium's socket connect.
Network browser actions therefore remain disabled until Aether has a pinned,
auditable egress proxy.
"""
from __future__ import annotations

from typing import Any


NETWORK_AUTOMATION_ENABLED = False
DISABLED_REASON = "egress_proxy_not_pinned"
_DISABLED_MESSAGE = (
    "Automação de navegador de rede desativada nesta versão: o Chromium não "
    "possui um proxy de saída com DNS/IP pinado. Use Pesquisa Profissional "
    "para leitura segura de páginas públicas."
)


def status() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": NETWORK_AUTOMATION_ENABLED,
        "reason": DISABLED_REASON,
        "detail": _DISABLED_MESSAGE,
    }


def _disabled() -> dict[str, Any]:
    return {
        "ok": False,
        "enabled": False,
        "blocked": True,
        "reason": DISABLED_REASON,
        "error": _DISABLED_MESSAGE,
    }


async def navigate(url: str, headless: bool = True) -> dict[str, Any]:
    del url, headless
    return _disabled()


async def screenshot(
    url: str,
    headless: bool = True,
    full_page: bool = False,
) -> dict[str, Any]:
    del url, headless, full_page
    return _disabled()


async def extract_text(url: str) -> dict[str, Any]:
    del url
    return _disabled()


async def click_element(url: str, selector: str) -> dict[str, Any]:
    del url, selector
    return _disabled()


async def fill_form(url: str, selector: str, value: str) -> dict[str, Any]:
    del url, selector, value
    return _disabled()
