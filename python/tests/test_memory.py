"""Tests for the memory subsystem."""
import tempfile
import unittest
from pathlib import Path


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Monkey-patch the DB path
        import jarvis.memory as mem
        self._orig_db = mem.settings.short_term_db_path
        mem.settings.short_term_db_path = self.tmpdir / "test_memory.sqlite3"
        mem._init_db()

    def tearDown(self):
        import jarvis.memory as mem
        mem.settings.short_term_db_path = self._orig_db
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_add_and_get_turn(self):
        import jarvis.memory as mem
        tid = mem.add_turn("user", "Hello", "session1")
        self.assertIsNotNone(tid)
        history = mem.get_short_term_history("session1", limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Hello")

    def test_multiple_sessions_isolated(self):
        import jarvis.memory as mem
        mem.add_turn("user", "Msg1", "session_a")
        mem.add_turn("user", "Msg2", "session_b")
        hist_a = mem.get_short_term_history("session_a")
        hist_b = mem.get_short_term_history("session_b")
        self.assertEqual(len(hist_a), 1)
        self.assertEqual(len(hist_b), 1)
        self.assertEqual(hist_a[0]["content"], "Msg1")
        self.assertEqual(hist_b[0]["content"], "Msg2")

    def test_set_and_get_facts(self):
        import jarvis.memory as mem
        mem.set_fact("user_name", "João")
        facts = mem.get_facts()
        self.assertEqual(facts.get("user_name"), "João")

    def test_reject_sensitive_fact(self):
        import jarvis.memory as mem
        with self.assertRaises(ValueError):
            mem.set_fact("api_key", "sk-1234")
        with self.assertRaises(ValueError):
            mem.set_fact("password", "secret123")

    def test_set_and_get_preferences(self):
        import jarvis.memory as mem
        mem.set_preference("theme", "dark")
        prefs = mem.get_preferences()
        self.assertEqual(prefs.get("theme"), "dark")

    def test_delete_turn(self):
        import jarvis.memory as mem
        tid = mem.add_turn("user", "Delete me", "session_del")
        self.assertTrue(mem.delete_turn(tid))
        history = mem.get_short_term_history("session_del")
        self.assertEqual(len(history), 0)

    def test_clear_session(self):
        import jarvis.memory as mem
        mem.add_turn("user", "A", "session_clear")
        mem.add_turn("assistant", "B", "session_clear")
        deleted = mem.clear_session("session_clear")
        self.assertEqual(deleted, 2)

    def test_list_sessions_returns_compact_summaries(self):
        import jarvis.memory as mem
        mem.add_turn("user", "Planeje meu projeto Aether", "session_summary")
        mem.add_turn("assistant", "Claro, vamos começar.", "session_summary")
        sessions = mem.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], "session_summary")
        self.assertEqual(sessions[0]["title"], "Planeje meu projeto Aether")
        self.assertEqual(sessions[0]["turn_count"], 2)
        self.assertIn("Claro", sessions[0]["preview"])

    def test_project_memory(self):
        import jarvis.memory as mem
        result = mem.set_project_memory("/tmp/proj", "decision1", "Use React", kind="decision")
        self.assertEqual(result["key"], "decision1")
        memories = mem.list_project_memories("/tmp/proj")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["value"], "Use React")

    def test_delete_fact(self):
        import jarvis.memory as mem
        mem.set_fact("test_key", "test_value")
        self.assertTrue(mem.delete_fact("test_key"))
        facts = mem.get_facts()
        self.assertNotIn("test_key", facts)


if __name__ == "__main__":
    unittest.main()
