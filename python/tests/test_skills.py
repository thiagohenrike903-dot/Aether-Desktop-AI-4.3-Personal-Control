"""Tests for the skills system."""
import tempfile
import unittest
from pathlib import Path


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        import jarvis.skills as sk
        # Use a temporary database for testing
        import jarvis.config as cfg
        self._orig_db = cfg.settings.data_dir
        cfg.settings.data_dir = self.tmpdir
        sk._DB_PATH = self.tmpdir / "test_skills.sqlite3"
        sk._init()

    def tearDown(self):
        import jarvis.config as cfg
        cfg.settings.data_dir = self._orig_db
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_create_and_get_skill(self):
        import jarvis.skills as sk
        skill = sk.create_skill({
            "name": "Python Expert",
            "description": "Expert in Python development",
            "instructions": "Write clean Python code.",
            "priority": 80,
            "category": "Code",
            "scope": "global",
        })
        self.assertIn("id", skill)
        self.assertEqual(skill["name"], "Python Expert")
        fetched = sk.get_skill(skill["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Python Expert")

    def test_update_skill(self):
        import jarvis.skills as sk
        skill = sk.create_skill({"name": "Test", "priority": 50})
        updated = sk.update_skill(skill["id"], {"priority": 90})
        self.assertEqual(updated["priority"], 90)
        self.assertEqual(updated["version"], 2)

    def test_delete_skill_requires_confirmation(self):
        import jarvis.skills as sk
        skill = sk.create_skill({"name": "Delete Me"})
        result = sk.delete_skill(skill["id"], confirmed=False)
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("requires_confirmation"))

    def test_list_skills(self):
        import jarvis.skills as sk
        sk.create_skill({"name": "Skill A"})
        sk.create_skill({"name": "Skill B"})
        all_skills = sk.list_skills()
        self.assertGreaterEqual(len(all_skills), 2)

    def test_duplicate_skill(self):
        import jarvis.skills as sk
        original = sk.create_skill({"name": "Original", "priority": 70})
        dup = sk.duplicate_skill(original["id"])
        self.assertIn("cópia", dup["name"].lower())
        self.assertFalse(dup["enabled"])

    def test_export_import_skills(self):
        import jarvis.skills as sk
        sk.create_skill({"name": "Exportable Skill"})
        pack = sk.export_skills()
        self.assertEqual(pack.get("format"), "aether-skill-pack")
        imported = sk.import_skills(pack)
        self.assertGreaterEqual(len(imported), 1)

    def test_match_skills(self):
        import jarvis.skills as sk
        sk.create_skill({
            "name": "Python Helper",
            "description": "Helps with Python code",
            "triggers": ["python", "código"],
            "priority": 90,
        })
        matches = sk.match_skills("Preciso de ajuda com Python")
        self.assertGreaterEqual(len(matches), 1)
        self.assertTrue(any("Python" in m["name"] for m in matches))

    def test_revisions(self):
        import jarvis.skills as sk
        skill = sk.create_skill({"name": "Revisable", "priority": 50})
        sk.update_skill(skill["id"], {"priority": 60})
        revs = sk.revisions(skill["id"])
        self.assertGreaterEqual(len(revs), 1)

    def test_restore_revision(self):
        import jarvis.skills as sk
        skill = sk.create_skill({"name": "Restore Me", "priority": 30})
        sk.update_skill(skill["id"], {"priority": 80})
        revs = sk.revisions(skill["id"])
        restored = sk.restore_revision(skill["id"], revs[-1]["id"])
        self.assertEqual(restored["priority"], 30)


if __name__ == "__main__":
    unittest.main()
