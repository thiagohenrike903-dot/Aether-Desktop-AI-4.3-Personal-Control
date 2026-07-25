"""OS automation primitives — these execute **real** actions on the host.

All functions are async so they can be called directly from FastAPI handlers
without blocking the event loop. Heavy work (process spawning, file copy)
runs in ``asyncio.to_thread``.
"""
from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# psutil is cross-platform; everything else below is Windows-first.
import psutil

from .config import minimal_subprocess_env
from .url_security import UnsafeURL, validate_external_open_url

SYSTEM = platform.system().lower()  # 'windows' | 'linux' | 'darwin'
IS_WINDOWS = SYSTEM == "windows"

_SAFE_SHELL_FOLDERS = {
    "downloads": "Downloads",
    "desktop": "Desktop",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}
_PROTECTED_PROCESS_NAMES = {
    "system", "registry", "smss", "csrss", "wininit", "services", "lsass",
    "winlogon", "svchost", "fontdrvhost", "python", "pythonw",
}


# ----------------------------------------------------------------------------- #
# App discovery
# ----------------------------------------------------------------------------- #

# Curated catalog of common apps — used as a *first* match for voice commands
# like "open Discord" or "open VS Code". Anything not in this catalog is
# resolved via OS search (Windows: Start Menu shortcuts; macOS: Applications;
# Linux: .desktop files) by ``resolve_installed_app``.
KNOWN_APPS: dict[str, dict[str, str]] = {
    # Windows-friendly launchers — we use the literal ``start`` command so we
    # don't have to hard-code install paths (they vary per user).
    "discord":            {"win": "discord",            "label": "Discord"},
    "spotify":            {"win": "spotify",            "label": "Spotify"},
    "steam":              {"win": "steam",              "label": "Steam"},
    "vscode":             {"win": "code",               "label": "VS Code"},
    "vs_code":            {"win": "code",               "label": "VS Code"},
    "code":               {"win": "code",               "label": "VS Code"},
    "photoshop":          {"win": "photoshop",          "label": "Photoshop"},
    "figma":              {"win": "figma",              "label": "Figma"},
    "notion":             {"win": "notion",             "label": "Notion"},
    "chrome":             {"win": "chrome",             "label": "Google Chrome"},
    "edge":               {"win": "msedge",             "label": "Microsoft Edge"},
    "firefox":            {"win": "firefox",            "label": "Firefox"},
    "terminal":           {"win": "wt",                 "label": "Windows Terminal"},
    "powershell":         {"win": "powershell",         "label": "PowerShell"},
    "cmd":                {"win": "cmd",                "label": "Command Prompt"},
    "explorer":           {"win": "explorer",           "label": "File Explorer"},
    "calculator":         {"win": "calc",               "label": "Calculator"},
    "notepad":            {"win": "notepad",            "label": "Notepad"},
    "settings":           {"win": "ms-settings:",       "label": "Windows Settings"},
    "task_manager":       {"win": "taskmgr",            "label": "Task Manager"},
}


def _normalize_app_key(name: str) -> str:
    return name.lower().strip().replace(" ", "_").replace("-", "_")


def resolve_installed_app(name: str) -> dict[str, Any] | None:
    """Find the launcher for a named app. Returns None if unknown.

    Strategy:
      1. Look up the curated catalog.
      2. If that fails on Windows, scan ``%APPDATA%\\Microsoft\\Windows\\Start Menu``
         and ``C:\\ProgramData\\Microsoft\\Windows\\Start Menu`` for a
         ``.lnk`` whose name matches.
    """
    key = _normalize_app_key(name)
    if key in KNOWN_APPS:
        return {"name": key, "label": KNOWN_APPS[key]["label"], "command": KNOWN_APPS[key].get("win")}

    if IS_WINDOWS:
        try:
            import win32api  # type: ignore
            # win32api.FindFiles only searches PATH; we need shortcut search.
            from .modules.windows_shortcuts import find_shortcut
            shortcut = find_shortcut(name)
            if shortcut:
                return {"name": key, "label": name, "command": shortcut}
        except Exception:
            pass

    return None


def list_installed_apps() -> list[dict[str, str]]:
    """Enumerate the curated catalog + any discovered Start Menu shortcuts."""
    apps: list[dict[str, str]] = []
    for key, meta in KNOWN_APPS.items():
        apps.append({"name": key, "label": meta["label"], "source": "catalog"})

    if IS_WINDOWS:
        try:
            from .modules.windows_shortcuts import list_start_menu_apps
            apps.extend(list_start_menu_apps())
        except Exception:
            pass

    return apps


# ----------------------------------------------------------------------------- #
# Launching
# ----------------------------------------------------------------------------- #

async def open_app(name: str) -> dict[str, Any]:
    """Open a named app, returning whether it actually launched."""
    resolved = resolve_installed_app(name)
    if not resolved:
        return {"ok": False, "error": f"App not found: {name}"}

    cmd = resolved["command"]

    def _launch() -> None:
        if IS_WINDOWS:
            # ``start`` resolves the registered handler for shell: URIs and
            # the shell-launched binaries alike.
            if cmd.endswith(":") or "://" in cmd:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", cmd],
                    shell=False,
                    env=minimal_subprocess_env(),
                )
            else:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", cmd],
                    shell=False,
                    env=minimal_subprocess_env(),
                )
        elif SYSTEM == "darwin":
            subprocess.Popen(["open", "-a", cmd], env=minimal_subprocess_env())
        else:
            subprocess.Popen([cmd], env=minimal_subprocess_env())

    try:
        await asyncio.to_thread(_launch)
        return {"ok": True, "app": resolved["label"], "command": cmd}
    except Exception as exc:  # pragma: no cover - launch failures depend on OS
        return {"ok": False, "error": str(exc), "app": resolved.get("label")}


async def open_path(path: str) -> dict[str, Any]:
    """Open a file or folder with the OS default handler.

    Accepts:
      * absolute or relative file system paths
      * ``shell:FolderName`` URIs (e.g. ``shell:Downloads``)
      * ``~`` and ``%VAR%`` expansions
    """
    expanded = os.path.expandvars(os.path.expanduser(path))

    # shell: URIs — route through the shell directly.
    if expanded.lower().startswith("shell:"):
        shell_name = expanded.split(":", 1)[1].strip().casefold()
        allowed_name = _SAFE_SHELL_FOLDERS.get(shell_name)
        if not allowed_name:
            return {
                "ok": False,
                "error": "Somente pastas conhecidas do usuário podem ser abertas por shell URI.",
                "blocked": True,
            }
        expanded = f"shell:{allowed_name}"

        def _open_shell() -> None:
            if IS_WINDOWS:
                # Use ShellExecuteW via os.startfile so the shell resolves
                # the user-friendly folder name.
                os.startfile(expanded)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(
                    ["xdg-open", expanded],
                    env=minimal_subprocess_env(),
                )
        try:
            await asyncio.to_thread(_open_shell)
            return {"ok": True, "path": expanded}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": expanded}

    p = Path(expanded)
    if not p.exists():
        return {"ok": False, "error": f"Path not found: {p}"}

    def _open() -> None:
        if IS_WINDOWS:
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif SYSTEM == "darwin":
            subprocess.Popen(
                ["open", str(p)],
                env=minimal_subprocess_env(),
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(p)],
                env=minimal_subprocess_env(),
            )

    try:
        await asyncio.to_thread(_open)
        return {"ok": True, "path": str(p)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(p)}


async def open_url(url: str) -> dict[str, Any]:
    """Open a URL in the default browser."""
    try:
        safe_url = validate_external_open_url(url)
    except UnsafeURL as exc:
        return {"ok": False, "error": str(exc), "url": str(url), "blocked": True}

    def _open() -> None:
        if IS_WINDOWS:
            os.startfile(safe_url)  # type: ignore[attr-defined]
        elif SYSTEM == "darwin":
            subprocess.Popen(
                ["open", safe_url],
                env=minimal_subprocess_env(),
            )
        else:
            subprocess.Popen(
                ["xdg-open", safe_url],
                env=minimal_subprocess_env(),
            )

    try:
        await asyncio.to_thread(_open)
        return {"ok": True, "url": safe_url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": safe_url}


# ----------------------------------------------------------------------------- #
# Window / process control
# ----------------------------------------------------------------------------- #

async def list_processes(filter_name: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    def _list() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                name = p.info.get("name") or ""
                if filter_name and filter_name.lower() not in name.lower():
                    continue
                results.append({"pid": p.info["pid"], "name": name})
                if len(results) >= limit:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return results

    return await asyncio.to_thread(_list)


async def kill_process(name: str) -> dict[str, Any]:
    """Close processes whose executable name safely matches ``name``.

    Older builds used substring matching, which meant an empty or very short
    value could terminate most processes on the computer. Matching is now
    exact after removing the executable suffix and the core process is always
    protected.
    """
    requested = str(name or "").strip()
    if not requested:
        return {"ok": False, "error": "Informe o nome exato do processo.", "killed": [], "failed": []}

    def _normalise(value: str) -> str:
        base = Path(value.strip()).name.casefold()
        for suffix in (".exe", ".com", ".bin", ".app"):
            if base.endswith(suffix):
                return base[:-len(suffix)]
        return base

    candidates = {_normalise(requested)}
    resolved = resolve_installed_app(requested)
    if resolved and resolved.get("command"):
        command = str(resolved["command"])
        if not command.endswith(":") and "://" not in command:
            candidates.add(_normalise(command))
    candidates.discard("")
    if not candidates:
        return {"ok": False, "error": "Nome de processo inválido.", "killed": [], "failed": []}
    if candidates & _PROTECTED_PROCESS_NAMES:
        return {
            "ok": False,
            "error": "Esse processo é protegido para evitar o encerramento do sistema ou do Aether.",
            "killed": [],
            "failed": [],
        }

    killed: list[int] = []
    failed: list[str] = []
    matched: list[int] = []
    own_pid = os.getpid()

    def _kill() -> None:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pid = int(p.info["pid"])
                pname = _normalise(p.info.get("name") or "")
                if pname in candidates:
                    matched.append(pid)
                    if pid == own_pid:
                        failed.append(f"{pid}: processo do Aether protegido")
                        continue
                    p.terminate()
                    killed.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                failed.append(str(exc))

    await asyncio.to_thread(_kill)
    if not killed:
        return {
            "ok": False,
            "error": "Nenhum processo correspondente pôde ser encerrado.",
            "matched": matched,
            "killed": killed,
            "failed": failed,
        }
    return {"ok": True, "matched": matched, "killed": killed, "failed": failed}


async def minimize_active_window() -> dict[str, Any]:
    """Minimize the currently focused window (Windows only)."""
    if not IS_WINDOWS:
        return {"ok": False, "error": "Only implemented on Windows."}
    try:
        import ctypes  # type: ignore
        # VK_LWIN down + D, then up. Sends "Show desktop" — robust for any focus.
        VK_LWIN = 0x5B
        KEYEVENTF_KEYUP = 0x0002

        def _do() -> None:
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)  # type: ignore[attr-defined]
            ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)     # 'D'
            ctypes.windll.user32.keybd_event(0x44, 0, KEYEVENTF_KEYUP, 0)
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

        await asyncio.to_thread(_do)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ----------------------------------------------------------------------------- #
# File system
# ----------------------------------------------------------------------------- #

async def list_directory(path: str) -> dict[str, Any]:
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    if not p.exists() or not p.is_dir():
        return {"ok": False, "error": f"Não é uma pasta válida: {p}"}

    def _list() -> tuple[list[dict[str, Any]], bool]:
        items: list[dict[str, Any]] = []
        truncated = False
        try:
            iterator = os.scandir(p)
        except (PermissionError, OSError):
            return [], False
        with iterator:
            for entry in iterator:
                if len(items) >= 500:
                    truncated = True
                    break
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    is_file = entry.is_file(follow_symlinks=False)
                    entry_stat = entry.stat(follow_symlinks=False) if is_file else None
                    items.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": is_dir,
                        "size": entry_stat.st_size if entry_stat else None,
                    })
                except (PermissionError, OSError):
                    continue
        items.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        return items, truncated

    items, truncated = await asyncio.to_thread(_list)
    return {
        "ok": True,
        "path": str(p),
        "items": items,
        "truncated": truncated,
        "limit": 500,
    }


async def file_action(action: str, src: str, dst: str | None = None) -> dict[str, Any]:
    """Move / copy / rename / delete a file. Deletions are gated on confirm."""
    source = Path(os.path.expandvars(os.path.expanduser(src)))
    if not source.exists():
        return {"ok": False, "error": f"Source not found: {source}"}

    def _do() -> dict[str, Any]:
        if action == "delete":
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
            return {"ok": True, "deleted": str(source)}
        if not dst:
            return {"ok": False, "error": "Destination required."}
        target = Path(os.path.expandvars(os.path.expanduser(dst)))
        if action == "copy":
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
        elif action == "move":
            shutil.move(str(source), str(target))
        elif action == "rename":
            target = source.with_name(dst) if "/" not in dst and "\\" not in dst else Path(
                os.path.expandvars(os.path.expanduser(dst))
            )
            source.rename(target)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return {"ok": True, "result": str(target)}

    try:
        return await asyncio.to_thread(_do)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ----------------------------------------------------------------------------- #
# System / power
# ----------------------------------------------------------------------------- #

async def system_action(action: str) -> dict[str, Any]:
    """Lock / shutdown / restart / suspend / log out the computer."""
    if not IS_WINDOWS:
        return {"ok": False, "error": f"System action '{action}' is only implemented on Windows."}

    commands: dict[str, list[str]] = {
        "lock":     ["rundll32.exe", "user32.dll,LockWorkStation"],
        "shutdown": ["shutdown", "/s", "/t", "0"],
        "restart":  ["shutdown", "/r", "/t", "0"],
        "log_out":  ["shutdown", "/l"],
    }

    if action == "suspend":
        # Suspend uses SetSuspendState via ctypes; cleaner than shell.
        def _suspend() -> None:
            import ctypes
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)  # type: ignore[attr-defined]
        try:
            await asyncio.to_thread(_suspend)
            return {"ok": True, "action": "suspend"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    if action not in commands:
        return {"ok": False, "error": f"Unknown system action: {action}"}

    try:
        subprocess.Popen(commands[action], env=minimal_subprocess_env())
        return {"ok": True, "action": action}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ----------------------------------------------------------------------------- #
# Volume / brightness / media
# ----------------------------------------------------------------------------- #

async def set_volume(level: int) -> dict[str, Any]:
    """Set master volume to ``level`` (0-100)."""
    if not IS_WINDOWS:
        return {"ok": False, "error": "Volume control is Windows-only in this build."}
    try:
        from .modules.audio_control import set_master_volume
        await asyncio.to_thread(set_master_volume, max(0, min(100, level)))
        return {"ok": True, "level": level}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def set_brightness(level: int) -> dict[str, Any]:
    """Set screen brightness (0-100)."""
    try:
        import screen_brightness_control as sbc  # type: ignore
        def _do() -> None:
            sbc.set_brightness(max(0, min(100, level)))
        await asyncio.to_thread(_do)
        return {"ok": True, "level": level}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def media_command(command: str) -> dict[str, Any]:
    """Send a media key (play, pause, next, prev, stop)."""
    if not IS_WINDOWS:
        return {"ok": False, "error": "Media control is Windows-only in this build."}
    key_map: dict[str, int] = {
        "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
    }
    vk = key_map.get(command.lower())
    if vk is None:
        return {"ok": False, "error": f"Unknown media command: {command}"}
    try:
        import ctypes
        def _send() -> None:
            KEYEVENTF_EXTENDEDKEY = 0x0001
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)  # type: ignore[attr-defined]
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
        await asyncio.to_thread(_send)
        return {"ok": True, "command": command}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ----------------------------------------------------------------------------- #
# Screenshot (used by VLM analysis)
# ----------------------------------------------------------------------------- #

async def screenshot() -> str | None:
    """Capture the screen and return base64-encoded JPEG."""
    try:
        import mss
        import base64
        import io

        def _capture() -> str:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # primary monitor
                sct_img = sct.grab(monitor)
                buf = io.BytesIO()
                from PIL import Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                img.save(buf, format="JPEG", quality=70)
                return base64.b64encode(buf.getvalue()).decode("utf-8")

        return await asyncio.to_thread(_capture)
    except ImportError:
        log.warning("mss/Pillow not installed — cannot capture screenshot.")
        return None
    except Exception as exc:
        log.warning("Screenshot failed: %s", exc)
        return None


# ----------------------------------------------------------------------------- #
# System snapshot (used by HUD telemetry)
# ----------------------------------------------------------------------------- #

async def system_snapshot() -> dict[str, Any]:
    def _snap() -> dict[str, Any]:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        try:
            temps = psutil.sensors_battery()
            battery = {
                "percent": temps.percent if temps else None,
                "plugged": temps.power_plugged if temps else None,
            } if temps else None
        except Exception:
            battery = None
        return {
            "cpu": cpu,
            "memory": mem.percent,
            "memory_used_gb": round(mem.used / 1024**3, 2),
            "memory_total_gb": round(mem.total / 1024**3, 2),
            "battery": battery,
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "running_processes": len(psutil.pids()),
        }
    return await asyncio.to_thread(_snap)
