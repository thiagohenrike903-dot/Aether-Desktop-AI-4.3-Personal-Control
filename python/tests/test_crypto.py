"""Tests for the file crypto module."""
import tempfile
import unittest
from pathlib import Path


class TestFileCrypto(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.test_file = self.tmpdir / "secret.txt"
        self.test_file.write_text("Conteúdo ultra secreto do Aether!")
        # Patch key file location
        import jarvis.file_crypto as crypto
        crypto._KEY_FILE = self.tmpdir / "test_key.bin"

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmpdir), ignore_errors=True)

    def test_encrypt_decrypt_file(self):
        import jarvis.file_crypto as crypto
        import asyncio
        enc = asyncio.run(crypto.encrypt_file(str(self.test_file)))
        self.assertTrue(enc.get("ok"))
        enc_path = Path(enc["encrypted"])
        self.assertTrue(enc_path.exists())
        self.assertNotEqual(enc_path.read_bytes(), self.test_file.read_bytes())
        conflict = asyncio.run(crypto.decrypt_file(str(enc_path)))
        self.assertTrue(conflict.get("conflict"))
        self.assertTrue(conflict.get("requires_overwrite"))
        dec = asyncio.run(crypto.decrypt_file(str(enc_path), overwrite=True))
        self.assertTrue(dec.get("ok"))
        dec_path = Path(dec["decrypted"])
        self.assertEqual(dec_path.read_text(), "Conteúdo ultra secreto do Aether!")

    def test_encrypt_does_not_overwrite_without_opt_in(self):
        import jarvis.file_crypto as crypto
        import asyncio
        output = self.test_file.with_suffix(".txt.aether")
        output.write_bytes(b"keep-me")
        result = asyncio.run(crypto.encrypt_file(str(self.test_file)))
        self.assertTrue(result.get("conflict"))
        self.assertEqual(output.read_bytes(), b"keep-me")

    def test_encrypt_decrypt_text(self):
        import jarvis.file_crypto as crypto
        import asyncio
        enc = asyncio.run(crypto.encrypt_text("Texto secreto"))
        self.assertTrue(enc.get("ok"))
        dec = asyncio.run(crypto.decrypt_text(enc["encrypted_b64"]))
        self.assertTrue(dec.get("ok"))
        self.assertEqual(dec["text"], "Texto secreto")

    def test_decrypt_nonexistent_file(self):
        import jarvis.file_crypto as crypto
        import asyncio
        result = asyncio.run(crypto.decrypt_file(str(self.tmpdir / "ghost.txt.aether")))
        self.assertFalse(result.get("ok"))

    def test_encrypt_nonexistent_file(self):
        import jarvis.file_crypto as crypto
        import asyncio
        result = asyncio.run(crypto.encrypt_file(str(self.tmpdir / "nope.txt")))
        self.assertFalse(result.get("ok"))


if __name__ == "__main__":
    unittest.main()
