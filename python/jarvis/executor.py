from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from . import (
    browser_agent,
    calendar_client,
    email_client,
    file_crypto,
    file_organizer,
    git_integration,
    llm,
    os_control,
    pdf_processor,
    plugin_system,
    privacy_control,
    weather,
    web_search,
    workspace,
    workspace_backup,
)

log = logging.getLogger("jarvis.executor")


def _privacy_gate(action: dict[str, Any]) -> dict[str, Any] | None:
    """Attribute and block network-capable actions before they call a tool."""
    kind = str(action.get("type") or "").strip().lower()
    target = str(action.get("url") or action.get("target") or "").strip()
    conversation_id = str(action.get("conversation_id") or "").strip() or None
    if (
        kind in {"plugin_load", "plugin_reload", "plugin_install", "plugin_run"}
        and privacy_control.effective_mode(conversation_id)["mode"] == "local_only"
    ):
        return {
            "ok": False,
            "blocked": True,
            "privacy": privacy_control.effective_mode(conversation_id),
            "error": (
                "Plugins em processo não oferecem isolamento de rede e ficam "
                "indisponíveis no perfil 100% local."
            ),
        }
    endpoints = {
        "open_url": target,
        "search_web": "https://www.google.com",
        "web_search": "https://duckduckgo.com",
        "web_fetch": target,
        "email_list": "https://gmail.googleapis.com",
        "email_search": "https://gmail.googleapis.com",
        "email_send": "https://gmail.googleapis.com",
        "calendar_list": "https://www.googleapis.com/calendar/v3",
        "calendar_create": "https://www.googleapis.com/calendar/v3",
        "calendar_delete": "https://www.googleapis.com/calendar/v3",
        "weather": "https://api.openweathermap.org",
        "weather_forecast": "https://api.openweathermap.org",
        "browser_navigate": target,
        "browser_screenshot": target,
        "browser_extract": target,
        "browser_click": target,
        "browser_fill": target,
    }
    endpoint = endpoints.get(kind)
    if endpoint is None:
        return None
    categories_by_kind = {
        "open_url": ["requested_url"],
        "search_web": ["web_query"],
        "web_search": ["web_query"],
        "web_fetch": ["requested_url"],
        "email_list": ["connected_account_metadata"],
        "email_search": ["connected_account_metadata", "search_query"],
        "email_send": ["recipient", "subject", "message_body"],
        "calendar_list": ["calendar_metadata"],
        "calendar_create": ["calendar_event"],
        "calendar_delete": ["calendar_event_id"],
        "weather": ["city"],
        "weather_forecast": ["city"],
        "browser_navigate": ["requested_url"],
        "browser_screenshot": ["requested_url", "page_pixels"],
        "browser_extract": ["requested_url", "page_content"],
        "browser_click": ["requested_url", "selector"],
        "browser_fill": ["requested_url", "selector", "form_values"],
    }
    request_id = str(action.get("request_id") or "").strip() or None
    decision = privacy_control.network_decision(
        endpoint,
        provider=kind,
        conversation_id=conversation_id,
    )
    if conversation_id:
        privacy_control.record_flow(
            endpoint=endpoint,
            provider=kind,
            categories=categories_by_kind.get(kind, ["tool_context"]),
            conversation_id=conversation_id,
            request_id=request_id,
            decision=decision,
        )
    if decision["blocked"]:
        return {
            "ok": False,
            "blocked": True,
            "privacy": decision,
            "error": (
                "A operação de rede foi bloqueada pelo perfil de privacidade "
                "ativo."
            ),
        }
    return None


def assess_risk(action: dict[str, Any] | None) -> str:
    """Classify an action without executing it.

    This is shared by the legacy confirmation gate and the 4.1 permission /
    Control Centre layers so the UI and executor cannot disagree about risk.
    """
    if not action:
        return "low"
    kind = (action.get("type") or "").lower()
    target = action.get("target")
    risk = "low"
    if kind == "system_action" and str(target).lower() in {
        "shutdown", "restart", "suspend", "log_out",
    }:
        risk = "critical"
    elif kind in {
        "plugin_install", "plugin_load", "plugin_unload", "plugin_reload", "plugin_run",
    }:
        risk = "critical"
    elif kind in {
        "kill_app",
        "email_send",
        "calendar_create",
        "calendar_delete",
        "backup_create",
        "backup_restore",
        "browser_click",
        "browser_fill",
        "git_add",
        "git_commit",
        "git_push",
        "git_pull",
        "git_merge",
        "git_branch_create",
        "git_branch_checkout",
        "crypto_encrypt",
        "crypto_decrypt",
        "crypto_encrypt_text",
        "crypto_decrypt_text",
        "capture_and_analyze",
        "workspace_write",
        "workspace_create",
        "workspace_rename",
        "workspace_delete",
        "workspace_run",
        "undo_organize_files",
    }:
        risk = "high"
    elif kind == "system_action":
        risk = "high"
    elif kind == "file_operation" and action.get("operation") in {
        "copy", "move", "rename", "delete",
    }:
        risk = "high"
    elif kind in {"organize_files", "clean_temp_files"} and not bool(
        action.get("dry_run", True)
    ):
        risk = "high"
    return risk


async def run(action: dict[str, Any] | None, confirmed: bool = False) -> dict[str, Any]:
    if not action:
        return {"ok": False, "skipped": True, "reason": "no action"}

    kind = (action.get("type") or "").lower()
    target = action.get("target")

    # Targets can contain private paths, recipients or signed URLs. Audit the
    # action category without copying those values into persistent logs.
    log.info(
        "Executing action kind=%s target_present=%s",
        kind,
        target not in (None, ""),
    )

    risk = assess_risk(action)
    if risk != "low" and not confirmed:
        return {
            "ok": False,
            "pending_confirmation": True,
            "risk": risk,
            "action": action,
            "error": "Esta ação precisa de confirmação.",
        }
    if privacy_block := _privacy_gate(action):
        return privacy_block

    if kind == "open_app":
        return await os_control.open_app(str(target))
    if kind == "open_path":
        return await os_control.open_path(str(target))
    if kind == "open_url":
        return await os_control.open_url(str(target))
    if kind == "kill_app":
        return await os_control.kill_process(str(target))
    if kind == "system_action":
        return await os_control.system_action(str(target))
    if kind == "set_volume":
        return await os_control.set_volume(int(target))
    if kind == "set_volume_delta":
        try:
            from .modules.audio_control import get_master_volume
            import asyncio
            current = await asyncio.to_thread(get_master_volume)
        except Exception:
            current = -1
        if current < 0:
            return {"ok": False, "error": "Não foi possível consultar o volume atual."}
        new_level = max(0, min(100, current + int(target)))
        return await os_control.set_volume(new_level)
    if kind == "set_brightness":
        return await os_control.set_brightness(int(target))
    if kind == "media_command":
        return await os_control.media_command(str(target))
    if kind == "minimize_active_window":
        return await os_control.minimize_active_window()
    if kind == "list_processes":
        procs = await os_control.list_processes(target)
        return {"ok": True, "processes": procs}
    if kind == "system_snapshot":
        return {"ok": True, **await os_control.system_snapshot()}
    if kind == "list_installed_apps":
        import asyncio
        apps = await asyncio.to_thread(os_control.list_installed_apps)
        return {"ok": True, "apps": apps}
    if kind == "search_web":
        return await os_control.open_url(
            f"https://www.google.com/search?q={quote_plus(str(target))}"
        )
    if kind == "list_directory":
        return await os_control.list_directory(str(target))
    if kind == "organize_files":
        return await file_organizer.organize_folder(
            folder_path=str(target),
            by_type=action.get("by_type", True),
            by_date=action.get("by_date", False),
            dry_run=action.get("dry_run", True),
        )
    if kind == "clean_temp_files":
        return await file_organizer.clean_temp_files(
            folder_path=str(target),
            days_old=int(action.get("days_old", 30)),
            dry_run=action.get("dry_run", True),
        )
    if kind == "undo_organize_files":
        return await file_organizer.undo_last_organization(str(target))
    if kind == "file_operation":
        op = action.get("operation", "copy")
        src = action.get("source", "")
        dst = action.get("destination")
        return await os_control.file_action(op, src, dst)
    if kind == "workspace_set":
        return workspace.set_root(str(target))
    if kind == "workspace_write":
        return await workspace.write_file(
            str(target),
            str(action.get("content", "")),
            action.get("expected_sha256"),
        )
    if kind == "workspace_create":
        return await workspace.create_entry(
            str(target),
            str(action.get("kind", "file")),
        )
    if kind == "workspace_rename":
        return await workspace.rename_entry(
            str(target),
            str(action.get("destination", "")),
        )
    if kind == "workspace_delete":
        return await workspace.delete_entry(str(target), confirmed)
    if kind == "workspace_run":
        return await workspace.run_task(str(target))

    if kind == "capture_and_analyze":
        source = action.get("source", "screen")
        prompt = action.get("prompt", "Descreva o que você vê.")
        if source == "camera":
            return {"ok": False, "info": "Ative a câmera pelo frontend e use o endpoint /vision/analyze."}
        try:
            screenshot = await os_control.screenshot()
            if not screenshot:
                return {"ok": False, "error": "Não foi possível capturar a tela."}
            result = await llm.analyze_image_vlm(screenshot, prompt)
            return {"ok": True, "analysis": result or "Não foi possível analisar a imagem."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # --- NOVAS AÇÕES ------------------------------------------------------- #

    if kind == "web_search":
        query = action.get("query") or str(target or "")
        results = await web_search.search_and_summarize(query)
        return {"ok": True, **results}

    if kind == "web_fetch":
        url = action.get("url") or str(target or "")
        text = await web_search.fetch_page_text(url)
        if text:
            return {"ok": True, "url": url, "text": text}
        return {"ok": False, "error": f"Não foi possível acessar {url}"}

    # Git
    if kind == "git_status":
        return await git_integration.status(str(target))
    if kind == "git_log":
        return await git_integration.log(str(target))
    if kind == "git_diff":
        return await git_integration.diff(str(target), action.get("ref", "HEAD"))
    if kind == "git_add":
        return await git_integration.add(str(target), action.get("paths"))
    if kind == "git_commit":
        return await git_integration.commit(str(target), action.get("message", "Aether AI commit"))
    if kind == "git_push":
        return await git_integration.push(str(target), action.get("remote", "origin"), action.get("branch"))
    if kind == "git_pull":
        return await git_integration.pull(str(target), action.get("remote", "origin"), action.get("branch"))
    if kind == "git_branch":
        return await git_integration.branch_list(str(target))
    if kind == "git_branch_create":
        return await git_integration.branch_create(str(target), action.get("name", ""), action.get("base"))
    if kind == "git_branch_checkout":
        return await git_integration.branch_checkout(str(target), action.get("name", ""))
    if kind == "git_merge":
        return await git_integration.merge(str(target), action.get("branch", ""))

    # Email
    if kind == "email_list":
        return {"ok": True, "emails": await email_client.list_emails(
            max_results=action.get("max", 10),
            query=action.get("query", ""),
        )}
    if kind == "email_send":
        return await email_client.send_email(
            to=action.get("to", ""),
            subject=action.get("subject", ""),
            body=action.get("body", ""),
        )
    if kind == "email_search":
        return {"ok": True, "emails": await email_client.search_emails(
            query=action.get("query", ""),
            max_results=action.get("max", 10),
        )}

    # Calendar
    if kind == "calendar_list":
        return await calendar_client.list_events(
            max_results=int(action.get("max", 10)),
        )
    if kind == "calendar_create":
        return await calendar_client.create_event(
            summary=action.get("summary", ""),
            start_time=action.get("start_time", ""),
            end_time=action.get("end_time", ""),
            description=action.get("description", ""),
            location=action.get("location", ""),
            timezone_name=action.get("time_zone"),
        )
    if kind == "calendar_delete":
        return await calendar_client.delete_event(action.get("event_id", ""))

    # Weather
    if kind == "weather":
        return await weather.get_weather(city=action.get("city", ""))
    if kind == "weather_forecast":
        return await weather.get_forecast(city=action.get("city", ""), days=action.get("days", 3))

    # PDF
    if kind == "pdf_extract_text":
        return await pdf_processor.extract_text(str(target))
    if kind == "pdf_extract_tables":
        return await pdf_processor.extract_tables(str(target))
    if kind == "pdf_extract_images":
        return await pdf_processor.extract_images(str(target))

    # Crypto
    if kind == "crypto_encrypt":
        return await file_crypto.encrypt_file(
            str(target),
            overwrite=bool(action.get("overwrite", False)),
        )
    if kind == "crypto_decrypt":
        return await file_crypto.decrypt_file(
            str(target),
            overwrite=bool(action.get("overwrite", False)),
        )
    if kind == "crypto_encrypt_text":
        return await file_crypto.encrypt_text(action.get("text", ""))
    if kind == "crypto_decrypt_text":
        return await file_crypto.decrypt_text(action.get("encrypted_b64", ""))

    # Backup
    if kind == "backup_create":
        return await workspace_backup.create_backup(str(target))
    if kind == "backup_list":
        return await workspace_backup.list_backups()
    if kind == "backup_restore":
        return await workspace_backup.restore_backup(
            str(target),
            action.get("target_dir"),
            confirmed=confirmed,
            overwrite=bool(action.get("overwrite", False)),
        )

    # Plugin system
    if kind == "plugin_list":
        return {"ok": True, "plugins": await plugin_system.list_plugins()}
    if kind == "plugin_load":
        return await plugin_system.load_plugin(str(target), confirmed=confirmed)
    if kind == "plugin_unload":
        return await plugin_system.unload_plugin(str(target))
    if kind == "plugin_reload":
        return await plugin_system.reload_plugin(str(target), confirmed=confirmed)
    if kind == "plugin_install":
        return await plugin_system.install_plugin(str(target), confirmed=confirmed)
    if kind == "plugin_run":
        return await plugin_system.run_plugin_action(
            str(target),
            action.get("plugin_action", "run"),
            action.get("params"),
            confirmed=confirmed,
        )

    # Browser automation
    if kind == "browser_navigate":
        return await browser_agent.navigate(str(target), headless=action.get("headless", True))
    if kind == "browser_screenshot":
        return await browser_agent.screenshot(str(target), headless=action.get("headless", True))
    if kind == "browser_extract":
        return await browser_agent.extract_text(str(target))
    if kind == "browser_click":
        return await browser_agent.click_element(str(target), action.get("selector", ""))
    if kind == "browser_fill":
        return await browser_agent.fill_form(str(target), action.get("selector", ""), action.get("value", ""))

    return {"ok": False, "error": f"Unknown action type: {kind}"}


async def undo(action: dict[str, Any], _result: dict[str, Any]) -> dict[str, Any]:
    """Undo only operations for which the core has a verified inverse."""
    kind = str(action.get("type") or "").lower()
    if kind == "organize_files" and not bool(action.get("dry_run", True)):
        return await file_organizer.undo_last_organization(str(action.get("target") or ""))
    return {
        "ok": False,
        "error": "Esta operação não possui um desfazer seguro implementado.",
    }
