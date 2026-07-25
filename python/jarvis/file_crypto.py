from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.crypto")

_KEY_FILE = settings.data_dir / "aether_key.bin"
_MAX_FILE_BYTES = 256 * 1024 * 1024
_MAX_TEXT_BYTES = 2 * 1024 * 1024


def _get_or_create_key() -> bytes:
    from cryptography.fernet import Fernet
    if _KEY_FILE.exists():
        if _KEY_FILE.is_symlink():
            raise ValueError("O arquivo de chave não pode ser um link simbólico.")
        return _KEY_FILE.read_bytes()

    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            _KEY_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        if _KEY_FILE.is_symlink():
            raise ValueError("O arquivo de chave não pode ser um link simbólico.")
        return _KEY_FILE.read_bytes()
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
        handle.flush()
        os.fsync(handle.fileno())
    return key


def _atomic_write(path: Path, data: bytes, overwrite: bool) -> None:
    """Write sensitive output completely before making it visible."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # A hard link gives us an atomic no-clobber commit on the same
            # filesystem. The temporary name is then removed.
            os.link(temporary, path)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def _validate_input_file(file_path: str) -> tuple[Path | None, dict[str, Any] | None]:
    raw_path = Path(file_path).expanduser()
    if not raw_path.exists():
        return None, {"ok": False, "error": "Arquivo não encontrado."}
    if raw_path.is_symlink():
        return None, {
            "ok": False,
            "blocked": True,
            "error": "Links simbólicos não são aceitos para criptografia.",
        }
    path = raw_path.resolve()
    if not path.is_file():
        return None, {"ok": False, "error": "O caminho precisa apontar para um arquivo."}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, {"ok": False, "error": str(exc)}
    if size > _MAX_FILE_BYTES:
        return None, {
            "ok": False,
            "blocked": True,
            "error": "O arquivo excede o limite de 256 MB.",
        }
    return path, None


def _conflict(path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "conflict": True,
        "requires_overwrite": True,
        "output": str(path),
        "error": "O arquivo de saída já existe.",
    }


async def encrypt_file(file_path: str, overwrite: bool = False) -> dict[str, Any]:
    from cryptography.fernet import Fernet
    path, error = _validate_input_file(file_path)
    if error:
        return error
    assert path is not None
    out_path = path.with_suffix(path.suffix + ".aether")
    if out_path.exists() and not overwrite:
        return _conflict(out_path)
    try:
        key = await asyncio.to_thread(_get_or_create_key)
        f = Fernet(key)

        def _do() -> dict[str, Any]:
            data = path.read_bytes()
            encrypted = f.encrypt(data)
            try:
                _atomic_write(out_path, encrypted, overwrite)
            except FileExistsError:
                return _conflict(out_path)
            return {
                "ok": True,
                "original": str(path),
                "encrypted": str(out_path),
                "original_size": len(data),
                "encrypted_size": len(encrypted),
            }
        return await asyncio.to_thread(_do)
    except ImportError:
        return {"ok": False, "error": "cryptography not installed. Run: pip install cryptography"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def decrypt_file(file_path: str, overwrite: bool = False) -> dict[str, Any]:
    from cryptography.fernet import Fernet, InvalidToken
    path, error = _validate_input_file(file_path)
    if error:
        return error
    assert path is not None
    if path.suffix.lower() != ".aether":
        return {"ok": False, "error": "O arquivo não parece estar criptografado (extensão .aether)."}
    out_path = path.with_suffix("")
    if out_path.exists() and not overwrite:
        return _conflict(out_path)
    try:
        key = await asyncio.to_thread(_get_or_create_key)
        f = Fernet(key)

        def _do() -> dict[str, Any]:
            data = path.read_bytes()
            decrypted = f.decrypt(data)
            try:
                _atomic_write(out_path, decrypted, overwrite)
            except FileExistsError:
                return _conflict(out_path)
            return {
                "ok": True,
                "encrypted": str(path),
                "decrypted": str(out_path),
                "size": len(decrypted),
            }
        return await asyncio.to_thread(_do)
    except InvalidToken:
        return {"ok": False, "error": "Chave inválida ou arquivo corrompido."}
    except ImportError:
        return {"ok": False, "error": "cryptography not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def encrypt_text(text: str) -> dict[str, Any]:
    from cryptography.fernet import Fernet
    encoded = text.encode("utf-8")
    if len(encoded) > _MAX_TEXT_BYTES:
        return {
            "ok": False,
            "blocked": True,
            "error": "O texto excede o limite de 2 MB.",
        }
    try:
        key = await asyncio.to_thread(_get_or_create_key)
        f = Fernet(key)
        encrypted = f.encrypt(encoded)
        return {
            "ok": True,
            "encrypted_b64": base64.b64encode(encrypted).decode(),
            "original_length": len(text),
        }
    except ImportError:
        return {"ok": False, "error": "cryptography not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def decrypt_text(encrypted_b64: str) -> dict[str, Any]:
    from cryptography.fernet import Fernet, InvalidToken
    if len(encrypted_b64) > (_MAX_TEXT_BYTES * 4):
        return {
            "ok": False,
            "blocked": True,
            "error": "O texto criptografado excede o limite aceito.",
        }
    try:
        key = await asyncio.to_thread(_get_or_create_key)
        f = Fernet(key)
        data = base64.b64decode(encrypted_b64, validate=True)
        decrypted = f.decrypt(data)
        if len(decrypted) > _MAX_TEXT_BYTES:
            return {
                "ok": False,
                "blocked": True,
                "error": "O texto descriptografado excede o limite de 2 MB.",
            }
        return {
            "ok": True,
            "text": decrypted.decode("utf-8"),
        }
    except InvalidToken:
        return {"ok": False, "error": "Chave inválida ou dados corrompidos."}
    except ImportError:
        return {"ok": False, "error": "cryptography not installed."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
