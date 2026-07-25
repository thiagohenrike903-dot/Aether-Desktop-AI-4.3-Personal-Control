"""Tests for the git integration module."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestGitIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo = self.tmpdir / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.repo), capture_output=True)
        test_file = self.repo / "readme.md"
        test_file.write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=str(self.repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=str(self.repo), capture_output=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_status(self):
        import jarvis.git_integration as git
        import asyncio
        result = asyncio.run(git.status(str(self.repo)))
        self.assertTrue(result.get("ok"))
        self.assertIn("master", result.get("branch", ""))

    def test_log(self):
        import jarvis.git_integration as git
        import asyncio
        result = asyncio.run(git.log(str(self.repo)))
        self.assertTrue(result.get("ok"))
        self.assertEqual(len(result.get("commits", [])), 1)
        self.assertEqual(result["commits"][0]["message"], "Initial")

    def test_add_and_commit(self):
        import jarvis.git_integration as git
        import asyncio
        (self.repo / "new.txt").write_text("new file")
        result = asyncio.run(git.commit(str(self.repo), "Add new.txt"))
        self.assertTrue(result.get("ok"))
        log = asyncio.run(git.log(str(self.repo)))
        self.assertEqual(len(log["commits"]), 2)

    def test_branch_list(self):
        import jarvis.git_integration as git
        import asyncio
        result = asyncio.run(git.branch_list(str(self.repo)))
        self.assertTrue(result.get("ok"))
        branches = result.get("branches", [])
        self.assertTrue(any(b["current"] for b in branches))

    def test_branch_create_and_checkout(self):
        import jarvis.git_integration as git
        import asyncio
        result = asyncio.run(git.branch_create(str(self.repo), "feature"))
        self.assertTrue(result.get("ok"))
        status = asyncio.run(git.status(str(self.repo)))
        self.assertEqual(status.get("branch"), "feature")


if __name__ == "__main__":
    unittest.main()
