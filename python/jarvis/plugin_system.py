from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import safety_mode
from .config import settings

logger = logging.getLogger("jarvis.plugins")

_PLUGIN_DIR = settings.data_dir / "plugins"
_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

_plugins: dict[str, dict[str, Any]] = {}
_plugin_handlers: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {}
_PLUGIN_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MAX_PLUGIN_BYTES = 2 * 1024 * 1024
_PLUGIN_TIMEOUT_SECONDS = 30
_MODULE_PREFIX = "aether_user_plugin_"
_IN_FLIGHT: set[str] = set()


def _valid_plugin_id(plugin_id: str) -> bool:
    return bool(_PLUGIN_ID.fullmatch(str(plugin_id or "")))


def _safe_module_path(module_path: str) -> Path | None:
    try:
        candidate = Path(module_path).resolve(strict=True)
        candidate.relative_to(_PLUGIN_DIR.resolve())
    except (OSError, ValueError):
        return None
    if not candidate.is_file() or candidate.suffix.casefold() != ".py":
        return None
    return candidate


def _confirmation(action: str, plugin_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "pending_confirmation": True,
        "requires_confirmation": True,
        "risk": "critical",
        "plugin_id": plugin_id,
        "action": action,
        "error": "Plugins executam código local e precisam de confirmação explícita.",
    }


def _suspended_result(action: str, plugin_id: str | None = None) -> dict[str, Any]:
    state = safety_mode.get_suspension("plugins")
    return {
        "ok": False,
        "blocked": True,
        "suspended": True,
        "action": action,
        "plugin_id": plugin_id,
        "suspension": state,
        "error": (
            "Plugins estão suspensos globalmente. Retome o componente antes "
            "de carregar, instalar ou executar plugins."
        ),
    }


async def list_plugins() -> list[dict[str, Any]]:
    suspended = safety_mode.is_suspended("plugins")
    return [
        {
            "id": pid,
            "name": info.get("name", pid),
            "version": info.get("version", "0.1.0"),
            "description": info.get("description", ""),
            "author": info.get("author", ""),
            "enabled": info.get("enabled", True),
            "loaded": pid in _plugin_handlers,
            "module_path": info.get("module_path", ""),
            "globally_suspended": suspended,
        }
        for pid, info in _plugins.items()
    ]


async def load_plugin(plugin_id: str, confirmed: bool = False) -> dict[str, Any]:
    if safety_mode.is_suspended("plugins"):
        return _suspended_result("load", plugin_id)
    if not _valid_plugin_id(plugin_id):
        return {"ok": False, "error": "Identificador de plugin inválido."}
    info = _plugins.get(plugin_id)
    if not info:
        return {"ok": False, "error": f"Plugin '{plugin_id}' não encontrado."}
    if plugin_id in _plugin_handlers:
        return {"ok": True, "plugin": info, "already_loaded": True}
    if not confirmed:
        return _confirmation("load", plugin_id)

    module_path = info.get("module_path", "")
    safe_path = _safe_module_path(str(module_path))
    if safe_path is None:
        return {"ok": False, "error": "O módulo do plugin não está no diretório permitido."}

    try:
        module_name = f"{_MODULE_PREFIX}{plugin_id}"
        sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(module_name, safe_path)
        if not spec or not spec.loader:
            return {"ok": False, "error": "Não foi possível carregar o módulo."}
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        handler = None
        if hasattr(module, "handler") and callable(module.handler):
            handler = module.handler
        elif hasattr(module, "PluginHandler"):
            handler_cls = module.PluginHandler()
            if hasattr(handler_cls, "handle") and callable(handler_cls.handle):
                handler = handler_cls.handle
        if handler is None:
            sys.modules.pop(module_name, None)
            return {"ok": False, "error": "Plugin não possui um handler compatível."}
        _plugin_handlers[plugin_id] = handler

        plugin_name = getattr(module, "PLUGIN_NAME", plugin_id)
        plugin_version = getattr(module, "PLUGIN_VERSION", "0.1.0")
        _plugins[plugin_id] = {**_plugins[plugin_id],
            "name": plugin_name,
            "version": plugin_version,
            "description": getattr(module, "PLUGIN_DESCRIPTION", info.get("description", "")),
            "author": getattr(module, "PLUGIN_AUTHOR", info.get("author", "")),
            "enabled": True,
            "loaded": True,
            "_module_name": module_name,
        }
        logger.info("Plugin loaded: %s v%s", plugin_name, plugin_version)
        return {"ok": True, "plugin": _plugins[plugin_id]}
    except Exception as exc:
        _plugin_handlers.pop(plugin_id, None)
        sys.modules.pop(f"{_MODULE_PREFIX}{plugin_id}", None)
        logger.error("Failed to load plugin %s: %s", plugin_id, exc)
        return {"ok": False, "error": str(exc)}


async def unload_plugin(plugin_id: str) -> dict[str, Any]:
    if plugin_id in _plugin_handlers:
        del _plugin_handlers[plugin_id]
    if plugin_id in _plugins:
        module_name = _plugins[plugin_id].get("_module_name")
        if module_name:
            sys.modules.pop(str(module_name), None)
        else:
            # Backward-compatible cleanup for plugins loaded by older builds,
            # without deleting an unrelated stdlib/third-party module.
            legacy = sys.modules.get(plugin_id)
            if legacy and Path(str(getattr(legacy, "__file__", ""))).resolve() == Path(
                str(_plugins[plugin_id].get("module_path", ""))
            ).resolve():
                sys.modules.pop(plugin_id, None)
        _plugins[plugin_id]["loaded"] = False
        _plugins[plugin_id]["enabled"] = False
    return {"ok": True, "plugin_id": plugin_id}


async def reload_plugin(plugin_id: str, confirmed: bool = False) -> dict[str, Any]:
    if safety_mode.is_suspended("plugins"):
        return _suspended_result("reload", plugin_id)
    if not confirmed:
        return _confirmation("reload", plugin_id)
    await unload_plugin(plugin_id)
    return await load_plugin(plugin_id, confirmed=True)


async def install_plugin(file_path: str, confirmed: bool = False) -> dict[str, Any]:
    if safety_mode.is_suspended("plugins"):
        return _suspended_result("install")
    src = Path(file_path)
    if not src.is_file() or src.is_symlink() or src.suffix.casefold() != ".py":
        return {"ok": False, "error": "O plugin precisa ser um arquivo .py."}
    plugin_id = src.stem
    if not _valid_plugin_id(plugin_id):
        return {
            "ok": False,
            "error": "O nome do plugin deve começar com uma letra e usar apenas letras, números, _ ou -.",
        }
    try:
        if src.stat().st_size > _MAX_PLUGIN_BYTES:
            return {"ok": False, "error": "O plugin excede o limite de 2 MB."}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if not confirmed:
        return _confirmation("install", plugin_id)

    dst = _PLUGIN_DIR / f"{plugin_id}.py"
    if dst.exists():
        plugin_id = f"{plugin_id}_{uuid.uuid4().hex[:6]}"
        dst = _PLUGIN_DIR / f"{plugin_id}.py"
    import shutil
    shutil.copy2(str(src), str(dst))
    _plugins[plugin_id] = {
        "name": plugin_id,
        "version": "0.1.0",
        "description": "",
        "author": "",
        "enabled": True,
        "loaded": False,
        "module_path": str(dst),
        "installed_at": time.time(),
    }
    return {
        "ok": True,
        "installed": True,
        "plugin": _plugins[plugin_id],
        "requires_load_confirmation": True,
    }


async def run_plugin_action(
    plugin_id: str,
    action: str,
    params: dict[str, Any] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    if safety_mode.is_suspended("plugins"):
        return _suspended_result("run", plugin_id)
    if not _valid_plugin_id(plugin_id):
        return {"ok": False, "error": "Identificador de plugin inválido."}
    if not confirmed:
        return _confirmation("run", plugin_id)
    handler = _plugin_handlers.get(plugin_id)
    if not handler:
        return {
            "ok": False,
            "load_required": True,
            "error": f"Plugin '{plugin_id}' não carregado. Confirme o carregamento primeiro.",
        }
    run_id = str(uuid.uuid4())
    _IN_FLIGHT.add(run_id)
    try:
        if inspect.iscoroutinefunction(handler):
            result = await asyncio.wait_for(
                handler(action=action, params=params or {}),
                timeout=_PLUGIN_TIMEOUT_SECONDS,
            )
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(handler, action=action, params=params or {}),
                timeout=_PLUGIN_TIMEOUT_SECONDS,
            )
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=_PLUGIN_TIMEOUT_SECONDS)
        return result if isinstance(result, dict) else {"ok": True, "result": str(result)}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "O plugin excedeu o limite de 30 segundos."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        _IN_FLIGHT.discard(run_id)


async def suspend_all(reason: str = "") -> dict[str, Any]:
    """Emergency-stop automations/plugins and unregister loaded handlers."""
    state = safety_mode.suspend_all(reason)
    loaded = list(_plugin_handlers)
    for plugin_id in loaded:
        await unload_plugin(plugin_id)
    in_flight = len(_IN_FLIGHT)
    return {
        "ok": True,
        "suspended": True,
        "state": state,
        "components": state["components"],
        "unloaded_plugin_ids": loaded,
        "unloaded_count": len(loaded),
        "in_flight_count": in_flight,
        "in_flight_terminated": False,
        "note": (
            "Handlers registrados foram descarregados e novas execuções foram "
            "bloqueadas. Código Python que já estava executando dentro do "
            "processo não pode ser encerrado à força com segurança."
        ),
    }


def resume_all() -> dict[str, Any]:
    """Resume automations/plugins; plugins remain unloaded until reconfirmed."""
    state = safety_mode.resume_all()
    return {
        "ok": True,
        "suspended": False,
        "state": state,
        "note": "Plugins permanecem descarregados e exigem novo carregamento.",
    }


def discover_plugins() -> None:
    for py_file in _PLUGIN_DIR.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        plugin_id = py_file.stem
        if not _valid_plugin_id(plugin_id) or py_file.is_symlink():
            logger.warning("Ignoring plugin with unsafe name or path: %s", py_file.name)
            continue
        if plugin_id not in _plugins:
            _plugins[plugin_id] = {
                "name": plugin_id,
                "version": "0.1.0",
                "description": "",
                "author": "",
                "enabled": True,
                "loaded": False,
                "module_path": str(py_file),
                "discovered_at": time.time(),
            }


discover_plugins()
