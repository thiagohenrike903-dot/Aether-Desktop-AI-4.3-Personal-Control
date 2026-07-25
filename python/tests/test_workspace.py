"""Tests for the workspace sandbox module."""
import os
import tempfile
import unittest
from pathlib import Path


class TestWorkspaceSecurity(unittest.TestCase):
    """Verify that workspace.resolve_path rejects paths outside the workspace."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.workspace_root = self.tmpdir / "project"
        self.workspace_root.mkdir()
        # Simulate setting the workspace root
        self._orig_cwd = os.getcwd()
        os.chdir(str(self.workspace_root))

    def tearDown(self):
        os.chdir(self._orig_cwd)
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def _patch_workspace(self):
        """Monkey-patch workspace state to use our temp dir."""
        import jarvis.workspace as ws
        ws._STATE_FILE = self.tmpdir / "test_workspace.json"
        ws.set_root(str(self.workspace_root))
        return ws

    def test_resolve_path_within_workspace(self):
        ws = self._patch_workspace()
        nested = self.workspace_root / "sub" / "file.txt"
        nested.parent.mkdir(parents=True)
        nested.touch()
        resolved = ws.resolve_path("sub/file.txt")
        self.assertEqual(resolved, nested)

    def test_resolve_path_outside_workspace_raises(self):
        ws = self._patch_workspace()
        with self.assertRaises(ValueError):
            ws.resolve_path("../outside")

    def test_resolve_path_absolute_outside_raises(self):
        ws = self._patch_workspace()
        with self.assertRaises(ValueError):
            ws.resolve_path(str(self.tmpdir / "outside"))

    def test_sensitive_files_not_readable(self):
        ws = self._patch_workspace()
        import asyncio
        env_file = self.workspace_root / ".env"
        env_file.write_text("SECRET=123")
        result = asyncio.run(ws.read_file(".env"))
        self.assertFalse(result.get("ok"))
        self.assertIn("sens", result.get("error", "").lower())

    def test_common_secret_files_are_hidden_from_read_tree_and_search(self):
        ws = self._patch_workspace()
        import asyncio

        sensitive_names = (
            ".env.production",
            "server.key",
            "credentials.json",
            "secrets.yaml",
        )
        for name in sensitive_names:
            (self.workspace_root / name).write_text(
                f"UNIQUE_SECRET_{name}=private",
                encoding="utf-8",
            )
            result = asyncio.run(ws.read_file(name))
            self.assertFalse(result.get("ok"), name)
            self.assertIn("sens", result.get("error", "").lower())

        normal = self.workspace_root / "settings.json"
        normal.write_text("NORMAL_MARKER=visible", encoding="utf-8")
        self.assertTrue(asyncio.run(ws.read_file(normal.name)).get("ok"))
        tokenizer = self.workspace_root / "tokenizer.json"
        tokenizer.write_text('{"type": "normal vocabulary"}', encoding="utf-8")
        self.assertTrue(asyncio.run(ws.read_file(tokenizer.name)).get("ok"))

        tree_result = asyncio.run(ws.tree(depth=2))
        visible_names = {
            child["name"]
            for child in tree_result["tree"].get("children", [])
        }
        self.assertTrue(set(sensitive_names).isdisjoint(visible_names))
        self.assertIn(normal.name, visible_names)
        self.assertIn(tokenizer.name, visible_names)

        secret_search = asyncio.run(ws.search("UNIQUE_SECRET"))
        self.assertEqual(secret_search["results"], [])
        normal_search = asyncio.run(ws.search("NORMAL_MARKER"))
        self.assertTrue(
            any(item["path"] == normal.name for item in normal_search["results"])
        )

    def test_tree_excludes_node_modules(self):
        ws = self._patch_workspace()
        nm = self.workspace_root / "node_modules"
        nm.mkdir()
        (nm / "package.js").touch()
        import asyncio
        result = asyncio.run(ws.tree(depth=3))
        self.assertTrue(result.get("ok"))
        tree = result.get("tree", {})
        children = tree.get("children", [])
        self.assertFalse(any(c["name"] == "node_modules" for c in children))

    def test_write_file_creates_nested_dirs(self):
        ws = self._patch_workspace()
        import asyncio
        result = asyncio.run(ws.write_file("a/b/c/file.txt", "hello"))
        self.assertTrue(result.get("ok"))
        target = self.workspace_root / "a" / "b" / "c" / "file.txt"
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "hello")

    def test_delete_moves_to_trash(self):
        ws = self._patch_workspace()
        target = self.workspace_root / "delete_me.txt"
        target.write_text("bye")
        import asyncio
        result = asyncio.run(ws.delete_entry("delete_me.txt", confirmed=True))
        self.assertTrue(result.get("ok"))
        self.assertFalse(target.exists())
        self.assertTrue(result.get("recoverable"))


if __name__ == "__main__":
    unittest.main()
