from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import json
import os
import socket
import sys
import tempfile
import time
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

_HAS_HTTPX = importlib.util.find_spec("httpx") is not None
if not _HAS_HTTPX:
    httpx = types.ModuleType("httpx")
    httpx.__spec__ = importlib.machinery.ModuleSpec("httpx", loader=None)
    httpx.__aether_test_stub__ = True
    httpx.HTTPError = Exception
    sys.modules["httpx"] = httpx
if importlib.util.find_spec("bs4") is None:
    bs4 = types.ModuleType("bs4")
    bs4.__spec__ = importlib.machinery.ModuleSpec("bs4", loader=None)
    bs4.BeautifulSoup = object
    sys.modules["bs4"] = bs4
if importlib.util.find_spec("psutil") is None:
    psutil = types.ModuleType("psutil")
    psutil.__spec__ = importlib.machinery.ModuleSpec("psutil", loader=None)
    psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    psutil.AccessDenied = type("AccessDenied", (Exception,), {})
    psutil.process_iter = lambda *_args, **_kwargs: []
    sys.modules["psutil"] = psutil

from jarvis import (
    calendar_client,
    code_agent,
    email_client,
    os_control,
    plugin_system,
    workspace,
    workspace_backup,
)
from jarvis.url_security import UnsafeURL, validate_public_http_url


class URLSecurityTests(unittest.TestCase):
    def test_rejects_non_http_credentials_and_private_dns(self) -> None:
        with self.assertRaises(UnsafeURL):
            asyncio.run(validate_public_http_url("file:///etc/passwd"))
        with self.assertRaises(UnsafeURL):
            asyncio.run(validate_public_http_url("https://user:pass@example.com"))
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with patch("jarvis.url_security.socket.getaddrinfo", return_value=answers):
            with self.assertRaises(UnsafeURL):
                asyncio.run(validate_public_http_url("https://example.test"))

    def test_accepts_public_dns(self) -> None:
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]
        with patch("jarvis.url_security.socket.getaddrinfo", return_value=answers):
            result = asyncio.run(validate_public_http_url("https://example.com/path"))
        self.assertEqual(result, "https://example.com/path")

    def test_os_open_url_blocks_custom_schemes(self) -> None:
        result = asyncio.run(os_control.open_url("file:///tmp/private.txt"))
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])


class ProcessSafetyTests(unittest.TestCase):
    class _Process:
        def __init__(self, pid: int, name: str) -> None:
            self.info = {"pid": pid, "name": name}
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    def test_empty_process_name_is_rejected(self) -> None:
        result = asyncio.run(os_control.kill_process(""))
        self.assertFalse(result["ok"])
        self.assertEqual(result["killed"], [])

    def test_process_matching_is_exact(self) -> None:
        exact = self._Process(91001, "notepad.exe")
        partial = self._Process(91002, "notepad-helper.exe")
        with patch(
            "jarvis.os_control.psutil.process_iter",
            return_value=[exact, partial],
        ):
            result = asyncio.run(os_control.kill_process("notepad"))
        self.assertTrue(result["ok"])
        self.assertTrue(exact.terminated)
        self.assertFalse(partial.terminated)


class PluginSafetyTests(unittest.TestCase):
    def test_install_does_not_execute_and_load_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            marker = root / "executed.txt"
            source = root / "sample_plugin.py"
            source.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
                "async def handler(action: str, params: dict) -> dict:\n"
                "    return {'ok': True, 'action': action}\n",
                encoding="utf-8",
            )

            previous_dir = plugin_system._PLUGIN_DIR
            plugin_system._PLUGIN_DIR = plugin_dir
            plugin_system._plugins.clear()
            plugin_system._plugin_handlers.clear()
            try:
                pending = asyncio.run(plugin_system.install_plugin(str(source)))
                self.assertTrue(pending["pending_confirmation"])
                self.assertFalse(marker.exists())

                installed = asyncio.run(
                    plugin_system.install_plugin(str(source), confirmed=True)
                )
                self.assertTrue(installed["ok"])
                self.assertFalse(marker.exists())
                plugin_id = installed["plugin"]["name"]

                pending_load = asyncio.run(plugin_system.load_plugin(plugin_id))
                self.assertTrue(pending_load["pending_confirmation"])
                self.assertFalse(marker.exists())

                loaded = asyncio.run(
                    plugin_system.load_plugin(plugin_id, confirmed=True)
                )
                self.assertTrue(loaded["ok"])
                self.assertTrue(marker.exists())

                pending_run = asyncio.run(
                    plugin_system.run_plugin_action(plugin_id, "hello")
                )
                self.assertTrue(pending_run["pending_confirmation"])
                ran = asyncio.run(
                    plugin_system.run_plugin_action(
                        plugin_id,
                        "hello",
                        confirmed=True,
                    )
                )
                self.assertTrue(ran["ok"])
            finally:
                asyncio.run(plugin_system.unload_plugin("sample_plugin"))
                plugin_system._plugins.clear()
                plugin_system._plugin_handlers.clear()
                plugin_system._PLUGIN_DIR = previous_dir


class BackupSafetyTests(unittest.TestCase):
    def test_backup_excludes_secrets_and_restore_defaults_to_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            project = base / "project"
            backup_dir = base / "backups"
            project.mkdir()
            (project / "normal.txt").write_text("safe", encoding="utf-8")
            (project / ".env").write_text("SECRET=value", encoding="utf-8")
            previous_dir = workspace_backup._BACKUP_DIR
            workspace_backup._BACKUP_DIR = backup_dir
            try:
                created = asyncio.run(workspace_backup.create_backup(str(project)))
                self.assertTrue(created["ok"])
                with zipfile.ZipFile(created["backup_path"]) as archive:
                    names = archive.namelist()
                self.assertTrue(any(name.endswith("/normal.txt") for name in names))
                self.assertFalse(any(name.endswith("/.env") for name in names))

                pending = asyncio.run(
                    workspace_backup.restore_backup(
                        created["backup_path"],
                        str(base / "restore"),
                    )
                )
                self.assertTrue(pending["pending_confirmation"])
            finally:
                workspace_backup._BACKUP_DIR = previous_dir

    def test_zip_slip_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive_path = base / "malicious.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "blocked")
            target = base / "target"
            result = asyncio.run(
                workspace_backup.restore_backup(
                    str(archive_path),
                    str(target),
                    confirmed=True,
                )
            )
            self.assertFalse(result["ok"])
            self.assertTrue(result["blocked"])
            self.assertFalse((base / "escape.txt").exists())


class WorkspaceBindingTests(unittest.TestCase):
    def test_plan_cannot_be_applied_to_another_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first = base / "first"
            second = base / "second"
            data = base / "data"
            first.mkdir()
            second.mkdir()
            data.mkdir()
            previous_state = workspace._STATE_FILE
            previous_checkpoints = code_agent._CHECKPOINT_DIR
            previous_history = code_agent._HISTORY_FILE
            workspace._STATE_FILE = data / "workspace.json"
            code_agent._CHECKPOINT_DIR = data / "checkpoints"
            code_agent._HISTORY_FILE = data / "history.json"
            plan_id = "workspace-bound-plan"
            try:
                workspace.set_root(str(first))
                code_agent._PLANS[plan_id] = {
                    "id": plan_id,
                    "created_at": time.time(),
                    "workspace_root": str(first.resolve()),
                    "summary": "Criar arquivo",
                    "notes": [],
                    "changes": [{
                        "operation": "create",
                        "path": "created.txt",
                        "content": "content",
                        "old_sha256": None,
                    }],
                }
                workspace.set_root(str(second))
                result = asyncio.run(code_agent.apply(plan_id, confirmed=True))
                self.assertFalse(result["ok"])
                self.assertTrue(result["workspace_mismatch"])
                self.assertFalse((second / "created.txt").exists())
            finally:
                code_agent._PLANS.pop(plan_id, None)
                workspace._STATE_FILE = previous_state
                code_agent._CHECKPOINT_DIR = previous_checkpoints
                code_agent._HISTORY_FILE = previous_history

    def test_checkpoint_normalizes_payload_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            project = base / "project"
            data = base / "data"
            project.mkdir()
            data.mkdir()
            (project / "note.txt").write_text("safe", encoding="utf-8")
            previous_state = workspace._STATE_FILE
            previous_checkpoints = code_agent._CHECKPOINT_DIR
            previous_history = code_agent._HISTORY_FILE
            workspace._STATE_FILE = data / "workspace.json"
            code_agent._CHECKPOINT_DIR = data / "checkpoints"
            code_agent._HISTORY_FILE = data / "history.json"
            try:
                workspace.set_root(str(project))
                checkpoint_id = asyncio.run(code_agent._create_checkpoint(
                    [{"path": "folder/../note.txt"}],
                    "Normalizar caminho",
                ))
                checkpoint = code_agent._CHECKPOINT_DIR / checkpoint_id
                manifest = json.loads(
                    (checkpoint / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["files"][0]["path"], "note.txt")
                self.assertEqual(
                    (checkpoint / "files" / "note.txt").read_text(encoding="utf-8"),
                    "safe",
                )
            finally:
                workspace._STATE_FILE = previous_state
                code_agent._CHECKPOINT_DIR = previous_checkpoints
                code_agent._HISTORY_FILE = previous_history


class CredentialSeparationTests(unittest.TestCase):
    def test_gmail_and_calendar_use_separate_tokens(self) -> None:
        self.assertNotEqual(email_client._TOKEN_FILE, calendar_client._TOKEN_FILE)


@unittest.skipUnless(_HAS_HTTPX, "httpx not installed")
class WeatherCredentialTests(unittest.TestCase):
    def test_llm_key_is_not_reused_for_weather(self) -> None:
        from jarvis import weather

        with patch.dict(os.environ, {"LLM_API_KEY": "do-not-send"}, clear=True):
            result = asyncio.run(weather.get_weather("São Paulo"))
        self.assertFalse(result["ok"])
        self.assertIn("WEATHER_API_KEY", result["hint"])


if __name__ == "__main__":
    unittest.main()
