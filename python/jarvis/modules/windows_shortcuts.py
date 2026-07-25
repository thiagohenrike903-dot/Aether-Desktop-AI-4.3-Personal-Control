"""Windows Start-Menu shortcut enumeration + .lnk resolution.

Uses only the standard library plus pywin32 (already required for the rest
of the Windows-specific functionality). Returns a list of user-facing apps.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

_START_MENU_DIRS: list[Path] = []


def _candidate_dirs() -> list[Path]:
    global _START_MENU_DIRS
    if _START_MENU_DIRS:
        return _START_MENU_DIRS

    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    programdata = os.environ.get("PROGRAMDATA")
    if programdata:
        candidates.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    _START_MENU_DIRS = [d for d in candidates if d.exists()]
    return _START_MENU_DIRS


def _iter_shortcuts() -> Iterable[Path]:
    for d in _candidate_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".lnk"):
                    yield Path(root) / f


def _resolve_shortcut_target(lnk_path: Path) -> str | None:
    """Resolve a .lnk to its target path. Uses the Windows shell COM."""
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk_path))
        return shortcut.Targetpath or None
    except Exception:
        return None


def list_start_menu_apps() -> list[dict[str, str]]:
    apps: list[dict[str, str]] = []
    seen: set[str] = set()
    for lnk in _iter_shortcuts():
        name = lnk.stem
        if name in seen:
            continue
        seen.add(name)
        apps.append({
            "name": name.lower(),
            "label": name,
            "source": "start_menu",
            "path": str(lnk),
        })
    return apps


def find_shortcut(query: str) -> str | None:
    """Return a ``start <lnk>``-compatible target for a fuzzy app name."""
    q = query.lower().strip()
    if not q:
        return None
    for lnk in _iter_shortcuts():
        if q in lnk.stem.lower():
            return str(lnk)
    # Fall back to resolving the .lnk target and using that as the start arg.
    for lnk in _iter_shortcuts():
        if q in lnk.stem.lower():
            target = _resolve_shortcut_target(lnk)
            if target:
                return target
    return None
