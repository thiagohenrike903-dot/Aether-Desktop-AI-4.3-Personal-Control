from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from jarvis import workspace

if importlib.util.find_spec("psutil") is None:
    psutil = types.ModuleType("psutil")
    psutil.__spec__ = importlib.machinery.ModuleSpec("psutil", loader=None)
    psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    psutil.AccessDenied = type("AccessDenied", (Exception,), {})
    psutil.process_iter = lambda *_args, **_kwargs: []
    sys.modules["psutil"] = psutil
if importlib.util.find_spec("httpx") is None:
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

from jarvis.executor import run


class WorkspaceSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.data = Path(self.temp.name) / "data"
        self.root.mkdir()
        self.data.mkdir()
        workspace._STATE_FILE = self.data / "workspace.json"
        workspace.settings.data_dir = self.data
        result = workspace.set_root(str(self.root))
        self.assertTrue(result["ok"])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_path_escape_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            workspace.resolve_path("../outside.txt")

    def test_conflict_safe_write(self) -> None:
        target = self.root / "app.py"
        target.write_text("print('one')\n", encoding="utf-8")
        opened = asyncio.run(workspace.read_file("app.py"))
        target.write_text("print('two')\n", encoding="utf-8")
        result = asyncio.run(workspace.write_file(
            "app.py",
            "print('three')\n",
            expected_sha256=opened["sha256"],
        ))
        self.assertFalse(result["ok"])
        self.assertTrue(result["conflict"])
        self.assertEqual(target.read_text(encoding="utf-8"), "print('two')\n")

    def test_delete_requires_confirmation_and_is_recoverable(self) -> None:
        target = self.root / "notes.txt"
        target.write_text("important", encoding="utf-8")
        pending = asyncio.run(workspace.delete_entry("notes.txt"))
        self.assertTrue(pending["requires_confirmation"])
        self.assertTrue(target.exists())
        deleted = asyncio.run(workspace.delete_entry("notes.txt", confirmed=True))
        self.assertTrue(deleted["ok"])
        self.assertTrue(deleted["recoverable"])
        self.assertTrue(Path(deleted["trash"]).exists())


class ActionConfirmationTests(unittest.TestCase):
    def test_shutdown_is_not_executed_without_confirmation(self) -> None:
        action = {"type": "system_action", "target": "shutdown"}
        with patch("jarvis.executor.os_control.system_action", new=AsyncMock()) as call:
            result = asyncio.run(run(action))
            self.assertTrue(result["pending_confirmation"])
            call.assert_not_awaited()

    def test_confirmed_shutdown_reaches_executor(self) -> None:
        action = {"type": "system_action", "target": "shutdown"}
        with patch(
            "jarvis.executor.os_control.system_action",
            new=AsyncMock(return_value={"ok": True}),
        ) as call:
            result = asyncio.run(run(action, confirmed=True))
            self.assertTrue(result["ok"])
            call.assert_awaited_once_with("shutdown")

    def test_file_organization_execution_requires_confirmation(self) -> None:
        action = {
            "type": "organize_files",
            "target": "~/Downloads",
            "dry_run": False,
        }
        with patch(
            "jarvis.executor.file_organizer.organize_folder",
            new=AsyncMock(),
        ) as call:
            result = asyncio.run(run(action))
            self.assertTrue(result["pending_confirmation"])
            call.assert_not_awaited()

    def test_external_side_effects_require_confirmation(self) -> None:
        for action in (
            {"type": "email_send", "to": "person@example.com"},
            {"type": "browser_fill", "target": "https://example.com", "selector": "#x"},
            {"type": "plugin_run", "target": "example"},
            {"type": "backup_restore", "target": "backup.zip"},
        ):
            with self.subTest(action=action["type"]):
                result = asyncio.run(run(action))
                self.assertTrue(result["pending_confirmation"])


if __name__ == "__main__":
    unittest.main()
