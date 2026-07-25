from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

if importlib.util.find_spec("httpx") is None:
    sys.modules["httpx"] = types.ModuleType("httpx")

from jarvis import code_agent, memory, skills, task_manager, workspace


class SkillServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.previous = skills._DB_PATH
        skills._DB_PATH = Path(self.temp.name) / "skills.sqlite3"
        skills._init()

    def tearDown(self) -> None:
        skills._DB_PATH = self.previous
        self.temp.cleanup()

    def test_skill_is_versioned_and_matches_trigger(self) -> None:
        created = skills.create_skill({
            "name": "React seguro",
            "description": "Padrões de componentes React",
            "instructions": "Prefira componentes pequenos.",
            "triggers": ["react"],
            "priority": 80,
        })
        self.assertEqual(created["version"], 1)
        updated = skills.update_skill(created["id"], {
            "name": created["name"],
            "instructions": "Prefira componentes pequenos e testáveis.",
        })
        self.assertEqual(updated["version"], 2)
        self.assertEqual(len(skills.revisions(created["id"])), 1)
        matched = skills.match_skills("Refatore este componente React")
        self.assertEqual(matched[0]["id"], created["id"])

    def test_duplicate_starts_disabled(self) -> None:
        original = skills.create_skill({"name": "Python", "triggers": ["python"]})
        duplicate = skills.duplicate_skill(original["id"])
        self.assertFalse(duplicate["enabled"])
        self.assertIn("cópia", duplicate["name"])


class MemoryControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.previous = memory.settings.short_term_db_path
        memory.settings.short_term_db_path = Path(self.temp.name) / "memory.sqlite3"
        memory._init_db()

    def tearDown(self) -> None:
        memory.settings.short_term_db_path = self.previous
        self.temp.cleanup()

    def test_project_memory_can_be_created_and_deleted(self) -> None:
        item = memory.set_project_memory("/project", "database", "PostgreSQL", "decision")
        self.assertEqual(memory.list_project_memories("/project")[0]["value"], "PostgreSQL")
        self.assertTrue(memory.delete_project_memory(item["id"]))
        self.assertEqual(memory.list_project_memories("/project"), [])

    def test_secrets_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            memory.set_preference("api_key", "not-even-a-real-key")
        with self.assertRaises(ValueError):
            memory.set_fact("provider", "sk-example-secret")


class ProjectInspectionTests(unittest.TestCase):
    def test_preview_respects_gitignore_and_flags_sensitive_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".gitignore").write_text("generated/\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "app.tsx").write_text("export default 1\n", encoding="utf-8")
            (root / "generated").mkdir()
            (root / "generated" / "large.js").write_text("ignored\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=private\n", encoding="utf-8")
            (root / "package.json").write_text('{"scripts": {}}', encoding="utf-8")
            preview = workspace.inspect_root(str(root))
            self.assertTrue(preview["ok"])
            self.assertTrue(preview["gitignore"])
            self.assertEqual(preview["sensitive_count"], 1)
            self.assertIn("Node.js", preview["frameworks"])
            self.assertGreaterEqual(preview["ignored"], 1)


class ObservableTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_code_task_reports_real_configuration_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            data = Path(temp) / "data"
            root.mkdir()
            data.mkdir()
            previous_state = workspace._STATE_FILE
            workspace._STATE_FILE = data / "workspace.json"
            workspace.set_root(str(root))
            with patch("jarvis.code_agent.settings.gemini_api_key", None):
                created = task_manager.create_code_task("Crie um arquivo", [], "test")
                for _ in range(40):
                    await asyncio.sleep(0.01)
                    task = task_manager.get_task(created["id"])
                    if task and task["status"] in {"failed", "cancelled"}:
                        break
                self.assertIsNotNone(task)
                self.assertEqual(task["status"], "failed")
                self.assertTrue(any(event["type"] == "analysis" for event in task["events"]))
            workspace._STATE_FILE = previous_state


class CheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_apply_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            data = Path(temp) / "data"
            root.mkdir()
            data.mkdir()
            (root / "app.py").write_text("print('old')\n", encoding="utf-8")
            previous_state = workspace._STATE_FILE
            previous_checkpoints = code_agent._CHECKPOINT_DIR
            previous_history = code_agent._HISTORY_FILE
            workspace._STATE_FILE = data / "workspace.json"
            code_agent._CHECKPOINT_DIR = data / "checkpoints"
            code_agent._HISTORY_FILE = data / "history.json"
            workspace.set_root(str(root))
            opened = await workspace.read_file("app.py")
            plan_id = "test-plan"
            code_agent._PLANS[plan_id] = {
                "id": plan_id,
                "created_at": 9999999999,
                "summary": "Atualizar app",
                "notes": [],
                "changes": [{
                    "operation": "write",
                    "path": "app.py",
                    "content": "print('new')\n",
                    "old_sha256": opened["sha256"],
                }],
            }
            applied = await code_agent.apply(plan_id, True, ["app.py"])
            self.assertTrue(applied["ok"])
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "print('new')\n")
            undone = await code_agent.undo(applied["checkpoint_id"], True)
            self.assertTrue(undone["ok"])
            self.assertEqual((root / "app.py").read_text(encoding="utf-8"), "print('old')\n")
            workspace._STATE_FILE = previous_state
            code_agent._CHECKPOINT_DIR = previous_checkpoints
            code_agent._HISTORY_FILE = previous_history


if __name__ == "__main__":
    unittest.main()
