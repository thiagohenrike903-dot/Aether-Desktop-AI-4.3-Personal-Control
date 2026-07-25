from __future__ import annotations

import ast
import asyncio
import importlib.machinery
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

# Keep this focused suite runnable in the lightweight source-audit runtime.
# Production dependencies provide the real modules; these stubs are used only
# when optional packages have not been installed yet.
if importlib.util.find_spec("httpx") is None:
    httpx = types.ModuleType("httpx")
    httpx.__spec__ = importlib.machinery.ModuleSpec("httpx", loader=None)
    httpx.HTTPError = Exception
    httpx.AsyncClient = object
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

from jarvis import automations, executor, operations, permissions, safety_mode


class SafetyModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_paths = {
            safety_mode: safety_mode._DB_PATH,
            permissions: permissions._DB_PATH,
            operations: operations._DB_PATH,
            automations: automations._DB_PATH,
        }
        control_db = self.root / "control_center.sqlite3"
        safety_mode._DB_PATH = control_db
        permissions._DB_PATH = control_db
        operations._DB_PATH = control_db
        automations._DB_PATH = self.root / "automations.sqlite3"
        safety_mode._init_db()
        permissions._init_db()
        operations._init_db()
        automations._init_db()
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        permissions.reset_session()
        safety_mode.set_mode("normal")

    def tearDown(self) -> None:
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        permissions.reset_session()
        for module, path in self.original_paths.items():
            module._DB_PATH = path
        self.temporary.cleanup()

    def test_mode_is_persisted_and_invalid_values_are_rejected(self) -> None:
        changed = safety_mode.set_mode("confirm_all")
        self.assertEqual(changed["mode"], "confirm_all")
        safety_mode._init_db()
        self.assertEqual(safety_mode.get_mode(), "confirm_all")
        with self.assertRaises(ValueError):
            safety_mode.set_mode("unsafe")

    def test_registry_covers_every_executor_action_and_unknown_fails_closed(self) -> None:
        source = Path(executor.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        executor_kinds: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not isinstance(node.left, ast.Name) or node.left.id != "kind":
                continue
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(
                    comparator.value, str
                ):
                    executor_kinds.add(comparator.value)
                elif isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
                    executor_kinds.update(
                        element.value
                        for element in comparator.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    )
        self.assertTrue(executor_kinds)
        self.assertEqual(
            executor_kinds - safety_mode.KNOWN_ACTIONS,
            set(),
            "Todo tipo tratado pelo executor precisa de classificação explícita.",
        )
        self.assertTrue(
            safety_mode.READ_ONLY_ACTIONS.isdisjoint(
                safety_mode.MUTATING_ACTIONS
            )
        )
        self.assertEqual(
            safety_mode.READ_ONLY_ACTIONS | safety_mode.MUTATING_ACTIONS,
            safety_mode.KNOWN_ACTIONS,
        )
        self.assertEqual(
            safety_mode.classify_action({"type": "future_tool"}),
            "unknown",
        )

        # Normal mode preserves the legacy executor contract.
        self.assertEqual(safety_mode.decision("action:future_tool"), "allow")
        safety_mode.set_mode("confirm_all")
        self.assertEqual(safety_mode.decision("action:future_tool"), "block")
        safety_mode.set_mode("read_only")
        self.assertEqual(
            safety_mode.decision("action:future_tool", confirmed=True),
            "block",
        )

    def test_confirm_all_and_read_only_compose_with_scope_permissions(self) -> None:
        safety_mode.set_mode("confirm_all")
        permissions.set_policy("action:system_snapshot", "session_allow")
        self.assertEqual(
            permissions.decision("action:system_snapshot", risk="low"),
            "ask",
        )
        self.assertEqual(
            permissions.decision(
                "action:system_snapshot",
                risk="low",
                confirmed=True,
            ),
            "allow",
        )

        safety_mode.set_mode("read_only")
        permissions.set_policy("action:email_send", "session_allow")
        self.assertEqual(
            permissions.decision(
                "action:email_send",
                risk="high",
                confirmed=True,
            ),
            "block",
        )
        permissions.set_policy("action:system_snapshot", "block")
        self.assertEqual(
            permissions.decision(
                "action:system_snapshot",
                risk="low",
                confirmed=True,
            ),
            "block",
        )

    def test_operation_rechecks_global_mode_immediately_before_running(self) -> None:
        calls: list[str] = []

        async def runner(action, _confirmed):
            calls.append(action["type"])
            return {"ok": True}

        safety_mode.set_mode("read_only")
        blocked = operations.create(
            {"type": "workspace_write", "target": "notes.txt", "content": "x"},
            risk="high",
        )
        blocked_result = asyncio.run(
            operations.run_existing(blocked["id"], runner, confirmed=True)
        )
        self.assertEqual(blocked_result["state"], "failed")
        self.assertEqual(calls, [])
        self.assertIn(
            "safety_mode_block",
            {event["type"] for event in operations.events(blocked["id"])},
        )

        readable = operations.create(
            {"type": "system_snapshot"},
            risk="low",
        )
        readable_result = asyncio.run(
            operations.run_existing(readable["id"], runner, confirmed=True)
        )
        self.assertEqual(readable_result["state"], "completed")
        self.assertEqual(calls, ["system_snapshot"])

    def test_confirm_all_waits_then_runs_only_after_confirmation(self) -> None:
        calls: list[str] = []

        async def runner(action, _confirmed):
            calls.append(action["type"])
            return {"ok": True}

        safety_mode.set_mode("confirm_all")
        operation = operations.create({"type": "system_snapshot"}, risk="low")
        awaiting = asyncio.run(
            operations.run_existing(operation["id"], runner, confirmed=False)
        )
        self.assertEqual(awaiting["state"], "awaiting_approval")
        self.assertEqual(calls, [])

        completed = asyncio.run(
            operations.run_existing(operation["id"], runner, confirmed=True)
        )
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(calls, ["system_snapshot"])

    def test_retry_rechecks_read_only_and_does_not_call_runner(self) -> None:
        calls: list[str] = []

        async def runner(action, _confirmed):
            calls.append(action["type"])
            return {"ok": True}

        original = operations.create(
            {"type": "email_send", "to": "person@example.com"},
            risk="high",
        )
        operations.transition(original["id"], "failed", error="offline")
        safety_mode.set_mode("read_only")
        repeated = asyncio.run(operations.retry(original["id"], runner))
        self.assertEqual(repeated["state"], "failed")
        self.assertEqual(repeated["parent_id"], original["id"])
        self.assertEqual(calls, [])

    def test_blocked_automation_never_reaches_execution_callback(self) -> None:
        calls: list[dict[str, object]] = []

        async def execute_callback(action, confirmed, request_id, force_approval):
            calls.append(
                {
                    "action": action,
                    "confirmed": confirmed,
                    "request_id": request_id,
                    "force_approval": force_approval,
                }
            )
            return {"id": None, "state": "completed"}

        automation = automations.create(
            name="Write a file",
            trigger={"type": "manual"},
            action={
                "type": "workspace_write",
                "target": "notes.txt",
                "content": "private",
            },
            enabled=True,
            require_approval=False,
        )
        safety_mode.set_mode("read_only")
        simulation = asyncio.run(automations.simulate(automation["id"]))
        self.assertTrue(simulation["trigger_would_run"])
        self.assertFalse(simulation["would_run"])
        self.assertTrue(simulation["safety"]["blocked"])

        run = asyncio.run(
            automations.run(automation["id"], execute_callback)
        )
        self.assertEqual(run["state"], "failed")
        self.assertIsNone(run["operation_id"])
        self.assertEqual(calls, [])

    def test_automation_forces_approval_in_confirm_all(self) -> None:
        calls: list[dict[str, object]] = []

        async def execute_callback(action, confirmed, request_id, force_approval):
            calls.append(
                {
                    "action": action,
                    "confirmed": confirmed,
                    "request_id": request_id,
                    "force_approval": force_approval,
                }
            )
            return {"id": None, "state": "awaiting_approval"}

        automation = automations.create(
            name="Snapshot",
            trigger={"type": "manual"},
            action={"type": "system_snapshot"},
            enabled=True,
            require_approval=False,
        )
        safety_mode.set_mode("confirm_all")
        run = asyncio.run(
            automations.run(automation["id"], execute_callback)
        )
        self.assertEqual(run["state"], "awaiting_approval")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["force_approval"])

    def test_undo_is_blocked_or_requires_confirmation_without_calling_runner(self) -> None:
        calls: list[str] = []

        async def undo_runner(action, _result):
            calls.append(action["type"])
            return {"ok": True}

        operation = operations.create(
            {"type": "organize_files", "target": "files", "dry_run": False},
            risk="high",
        )
        operations.transition(operation["id"], "running")
        operations.transition(
            operation["id"],
            "completed",
            result={"ok": True},
        )

        safety_mode.set_mode("read_only")
        blocked = asyncio.run(operations.undo(operation["id"], undo_runner))
        self.assertTrue(blocked["blocked"])
        self.assertEqual(calls, [])

        safety_mode.set_mode("confirm_all")
        pending = asyncio.run(operations.undo(operation["id"], undo_runner))
        self.assertTrue(pending["pending_confirmation"])
        self.assertEqual(calls, [])

        completed = asyncio.run(
            operations.undo(
                operation["id"],
                undo_runner,
                confirmed=True,
            )
        )
        self.assertTrue(completed["ok"])
        self.assertEqual(calls, ["organize_files"])


if __name__ == "__main__":
    unittest.main()
