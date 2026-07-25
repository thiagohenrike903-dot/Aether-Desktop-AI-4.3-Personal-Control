"""Validated full-user backups with credentials excluded by construction."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .config import settings

_BACKUP_DIR = settings.data_dir / "user_backups"
_FORMAT = "aether-user-backup-v1"
_MAGIC = b"AETHERBKUP1\n"
_MAX_FILES = 25_000
_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
_MAX_FILE_BYTES = 1024 * 1024 * 1024
_COMPONENTS: dict[str, tuple[str, ...]] = {
    "projects": ("projects.sqlite3",),
    "conversations": ("conversations.sqlite3",),
    "memories": ("short_term.sqlite3", "vector_store"),
    "skills": ("skills.sqlite3",),
    "automations": ("automations.sqlite3",),
    "settings": (
        "personal_control.sqlite3",
        "control_center.sqlite3",
        "workspace.json",
        "recent_projects.json",
        "tasks.json",
        "code_history.json",
    ),
    "checkpoints": ("checkpoints",),
}
_DEFAULT_COMPONENTS = tuple(_COMPONENTS)
_SENSITIVE_NAMES = {
    "aether_key.bin",
    "gmail_credentials.json",
    "gmail_token.json",
    "calendar_token.json",
    "credentials.json",
    ".env",
    ".npmrc",
    ".pypirc",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}


def _sensitive(path: Path) -> bool:
    name = path.name.casefold()
    return bool(
        name in _SENSITIVE_NAMES
        or name.startswith(".env.")
        or path.suffix.casefold() in _SENSITIVE_SUFFIXES
        or any(token in name for token in ("credential", "private_key", "secret"))
    )


def _selected(value: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    items = tuple(dict.fromkeys(value or _DEFAULT_COMPONENTS))
    unknown = [item for item in items if item not in _COMPONENTS]
    if unknown:
        raise ValueError(f"Componente de backup inválido: {unknown[0]}")
    if not items:
        raise ValueError("Selecione ao menos um componente.")
    return items


def _iter_files(components: tuple[str, ...]) -> tuple[list[tuple[Path, str]], list[str]]:
    output: list[tuple[Path, str]] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for component in components:
        for relative in _COMPONENTS[component]:
            source = settings.data_dir / relative
            candidates = [source] if source.is_file() else (
                sorted(path for path in source.rglob("*") if path.is_file())
                if source.is_dir() else []
            )
            for path in candidates:
                if path.is_symlink() or _sensitive(path):
                    excluded.append(str(path.relative_to(settings.data_dir)))
                    continue
                try:
                    relative_path = path.resolve().relative_to(settings.data_dir.resolve())
                except (OSError, ValueError):
                    continue
                archive_name = relative_path.as_posix()
                if archive_name in seen or archive_name.startswith("user_backups/"):
                    continue
                seen.add(archive_name)
                output.append((path, archive_name))
    return output, sorted(set(excluded))


def preview(components: list[str] | None = None) -> dict[str, Any]:
    selected = _selected(components)
    files, excluded = _iter_files(selected)
    total = 0
    valid: list[dict[str, Any]] = []
    for path, archive_name in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        valid.append({"path": archive_name, "size": size})
    return {
        "ok": True,
        "components": list(selected),
        "files": len(valid),
        "total_bytes": total,
        "estimated_size_mb": round(total / (1024 * 1024), 2),
        "credentials_included": False,
        "excluded_sensitive": excluded,
        "items": valid[:500],
        "truncated_preview": len(valid) > 500,
    }


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    read = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    write = sqlite3.connect(destination)
    try:
        read.backup(write)
    finally:
        write.close()
        read.close()


def _derive_fernet(password: str, salt: bytes):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.fernet import Fernet

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))


def _encrypt(payload: bytes, password: str) -> bytes:
    if len(password) < 10:
        raise ValueError("A senha do backup precisa ter ao menos 10 caracteres.")
    salt = os.urandom(16)
    return _MAGIC + base64.urlsafe_b64encode(salt) + b"\n" + _derive_fernet(
        password, salt
    ).encrypt(payload)


def _decrypt(payload: bytes, password: str | None) -> bytes:
    if not payload.startswith(_MAGIC):
        return payload
    if not password:
        raise ValueError("Este backup é criptografado e exige a senha.")
    try:
        salt_line, token = payload[len(_MAGIC):].split(b"\n", 1)
        salt = base64.urlsafe_b64decode(salt_line)
        return _derive_fernet(password, salt).decrypt(token)
    except Exception as exc:
        raise ValueError("Senha inválida ou backup criptografado corrompido.") from exc


def create(
    *,
    components: list[str] | None = None,
    password: str | None = None,
    app_version: str = "unknown",
    reason: str = "manual",
) -> dict[str, Any]:
    selected = _selected(components)
    files, excluded = _iter_files(selected)
    if len(files) > _MAX_FILES:
        raise ValueError("O backup excede o limite de arquivos.")
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_id = str(uuid.uuid4())
    created_at = time.time()
    entries: list[dict[str, Any]] = []
    total = 0
    with tempfile.TemporaryDirectory(prefix="aether-user-backup-") as temp_value:
        temp = Path(temp_value)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, archive_name in files:
                try:
                    size = source.stat().st_size
                except OSError:
                    continue
                if size > _MAX_FILE_BYTES or total + size > _MAX_TOTAL_BYTES:
                    raise ValueError("O backup excede o limite de tamanho.")
                snapshot = source
                if source.suffix == ".sqlite3":
                    snapshot = temp / f"{uuid.uuid4().hex}.sqlite3"
                    _snapshot_sqlite(source, snapshot)
                data = snapshot.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                archive.writestr(f"data/{archive_name}", data)
                entries.append({
                    "path": archive_name,
                    "size": len(data),
                    "sha256": digest,
                })
                total += len(data)
            manifest = {
                "format": _FORMAT,
                "backup_id": backup_id,
                "app_version": str(app_version)[:80],
                "created_at": created_at,
                "reason": str(reason or "manual")[:120],
                "components": list(selected),
                "credentials_included": False,
                "excluded_sensitive": excluded,
                "files": entries,
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            )
        payload = zip_buffer.getvalue()
    encrypted = bool(password)
    if password:
        payload = _encrypt(payload, password)
    suffix = ".aether-backup" if encrypted else ".zip"
    filename = f"Aether-User-{time.strftime('%Y%m%d-%H%M%S')}-{backup_id[:8]}{suffix}"
    destination = _BACKUP_DIR / filename
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, destination)
    return {
        "ok": True,
        "id": backup_id,
        "filename": filename,
        "path": str(destination),
        "encrypted": encrypted,
        "components": list(selected),
        "files": len(entries),
        "size": len(payload),
        "credentials_included": False,
        "created_at": created_at,
    }


def list_backups() -> list[dict[str, Any]]:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    for path in sorted(
        [
            *list(_BACKUP_DIR.glob("Aether-User-*.zip")),
            *list(_BACKUP_DIR.glob("Aether-User-*.aether-backup")),
        ],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:200]:
        stat_value = path.stat()
        output.append({
            "id": path.stem.rsplit("-", 1)[-1],
            "filename": path.name,
            "path": str(path),
            "encrypted": path.suffix == ".aether-backup",
            "size": stat_value.st_size,
            "created_at": stat_value.st_mtime,
        })
    return output


def _resolve_backup(filename: str) -> Path:
    name = Path(str(filename or "")).name
    path = (_BACKUP_DIR / name).resolve()
    try:
        path.relative_to(_BACKUP_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Backup inválido.") from exc
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(name)
    return path


def _validated_archive(
    path: Path,
    *,
    password: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    payload = _decrypt(path.read_bytes(), password)
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("O arquivo não é um backup Aether válido.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_FILES + 1:
            raise ValueError("O backup contém arquivos demais.")
        names = {info.filename for info in infos}
        if "manifest.json" not in names:
            raise ValueError("O manifesto do backup está ausente.")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != _FORMAT:
            raise ValueError("Formato de backup incompatível.")
        total = 0
        listed = {item["path"]: item for item in manifest.get("files", [])}
        for info in infos:
            pure = PurePosixPath(info.filename)
            if (
                pure.is_absolute()
                or any(part in {"", ".", ".."} for part in pure.parts)
                or ((info.external_attr >> 16) & stat.S_IFMT(stat.S_IFLNK)) == stat.S_IFLNK
            ):
                raise ValueError("O backup possui um caminho inseguro.")
            if not info.filename.startswith("data/"):
                continue
            relative = info.filename[5:]
            expected = listed.get(relative)
            if not expected:
                raise ValueError("O backup contém um arquivo não manifestado.")
            if info.file_size > _MAX_FILE_BYTES:
                raise ValueError("Um arquivo do backup excede o limite.")
            data = archive.read(info)
            total += len(data)
            if total > _MAX_TOTAL_BYTES:
                raise ValueError("O backup excede o limite total.")
            if hashlib.sha256(data).hexdigest() != expected.get("sha256"):
                raise ValueError(f"Falha de integridade em {relative}.")
    return payload, manifest


def validate(filename: str, *, password: str | None = None) -> dict[str, Any]:
    path = _resolve_backup(filename)
    _, manifest = _validated_archive(path, password=password)
    return {
        "ok": True,
        "filename": path.name,
        "format": manifest["format"],
        "app_version": manifest.get("app_version"),
        "created_at": manifest.get("created_at"),
        "components": manifest.get("components", []),
        "files": len(manifest.get("files", [])),
        "credentials_included": False,
    }


def restore(
    filename: str,
    *,
    password: str | None = None,
    components: list[str] | None = None,
    confirmed: bool = False,
    current_version: str = "unknown",
) -> dict[str, Any]:
    if not confirmed:
        return {
            "ok": False,
            "pending_confirmation": True,
            "error": "A restauração altera dados locais e precisa de confirmação.",
        }
    path = _resolve_backup(filename)
    payload, manifest = _validated_archive(path, password=password)
    selected = _selected(components or manifest.get("components"))
    allowed_paths = {
        relative
        for component in selected
        for relative in _COMPONENTS[component]
    }
    pre_restore = create(
        components=list(selected),
        app_version=current_version,
        reason="pre_restore_snapshot",
    )
    restored: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aether-restore-") as temp_value:
        temp = Path(temp_value)
        originals = temp / "originals"
        staged = temp / "staged"
        originals.mkdir()
        staged.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                for item in manifest.get("files", []):
                    relative = str(item["path"])
                    if not any(
                        relative == root or relative.startswith(f"{root}/")
                        for root in allowed_paths
                    ):
                        continue
                    destination = (settings.data_dir / relative).resolve()
                    destination.relative_to(settings.data_dir.resolve())
                    if _sensitive(destination):
                        continue
                    data = archive.read(f"data/{relative}")
                    staged_file = staged / relative
                    staged_file.parent.mkdir(parents=True, exist_ok=True)
                    staged_file.write_bytes(data)
                    if destination.exists():
                        original = originals / relative
                        original.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(destination, original)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged_file, destination)
                    restored.append(relative)
        except Exception:
            for relative in reversed(restored):
                destination = settings.data_dir / relative
                original = originals / relative
                if original.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(original, destination)
                else:
                    destination.unlink(missing_ok=True)
            raise
    return {
        "ok": True,
        "restored": restored,
        "components": list(selected),
        "pre_restore_backup": pre_restore,
        "credentials_restored": False,
        "restart_required": True,
    }
