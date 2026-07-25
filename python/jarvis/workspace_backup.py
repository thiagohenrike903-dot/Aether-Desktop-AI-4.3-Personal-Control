from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import stat
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .config import settings

logger = logging.getLogger("jarvis.backup")

_BACKUP_DIR = settings.data_dir / "workspace_backups"
_MAX_BACKUPS = 20
_MAX_ARCHIVE_FILES = 20_000
_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ARCHIVE_FILE_BYTES = 512 * 1024 * 1024
_SENSITIVE_NAMES = {
    ".npmrc", ".pypirc", "credentials", "credentials.json",
    "gmail_credentials.json", "gmail_token.json", "calendar_token.json",
    "id_rsa", "id_ed25519", "known_hosts",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
_SENSITIVE_PARTS = {"secret", "secrets", "credential", "credentials", "private_key"}


def _backup_path(workspace_name: str) -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    unique = uuid.uuid4().hex[:8]
    return _BACKUP_DIR / f"{workspace_name}_{timestamp}_{unique}.zip"


def _sensitive_path(path: Path) -> bool:
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if name in _SENSITIVE_NAMES or path.suffix.casefold() in _SENSITIVE_SUFFIXES:
        return True
    return any(part in name for part in _SENSITIVE_PARTS)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


async def create_backup(workspace_root: str) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return {"ok": False, "error": "Workspace não encontrado."}

    name = root.name
    out_path = _backup_path(name)
    ignore_patterns = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".next", ".nuxt", "dist", "build", "target", ".idea",
        ".vscode", "*.pyc", ".DS_Store", "Thumbs.db",
    }

    def _zip() -> dict[str, Any]:
        count = 0
        total_size = 0
        skipped_sensitive = 0
        part_path = out_path.with_suffix(".zip.part")
        try:
            with zipfile.ZipFile(part_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for current, dirs, files in os.walk(root, followlinks=False):
                    current_path = Path(current)
                    kept_dirs: list[str] = []
                    for directory in dirs:
                        candidate = current_path / directory
                        if (
                            directory in ignore_patterns
                            or directory.startswith(".")
                            or candidate.is_symlink()
                            or _inside(candidate, settings.data_dir)
                            or _sensitive_path(candidate)
                        ):
                            if _sensitive_path(candidate):
                                skipped_sensitive += 1
                            continue
                        kept_dirs.append(directory)
                    dirs[:] = kept_dirs

                    for file in files:
                        fpath = current_path / file
                        if (
                            file in ignore_patterns
                            or file.endswith((".pyc", ".pyo"))
                            or fpath.is_symlink()
                        ):
                            continue
                        if _sensitive_path(fpath):
                            skipped_sensitive += 1
                            continue
                        try:
                            file_stat = fpath.stat(follow_symlinks=False)
                            if not stat.S_ISREG(file_stat.st_mode):
                                continue
                            file_size = max(0, file_stat.st_size)
                            if file_size > _MAX_ARCHIVE_FILE_BYTES:
                                raise ValueError(
                                    f"Arquivo grande demais para o backup: {fpath.name}"
                                )
                            if count + 1 > _MAX_ARCHIVE_FILES:
                                raise ValueError("O workspace contém arquivos demais para um backup.")
                            if total_size + file_size > _MAX_ARCHIVE_BYTES:
                                raise ValueError("O backup excederia o limite de 2 GB.")
                            arcname = fpath.relative_to(root.parent)
                            zf.write(fpath, arcname)
                            count += 1
                            total_size += file_size
                        except (PermissionError, OSError):
                            continue
            os.replace(part_path, out_path)
        finally:
            part_path.unlink(missing_ok=True)

        manifest = {
            "created_at": time.time(),
            "workspace": name,
            "root": str(root),
            "files": count,
            "total_size": total_size,
            "skipped_sensitive": skipped_sensitive,
            "backup_path": str(out_path),
        }
        manifest_path = out_path.with_suffix(".meta.json")
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return {
            "ok": True,
            "backup_path": str(out_path),
            "files": count,
            "size": total_size,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "skipped_sensitive": skipped_sensitive,
        }

    try:
        result = await asyncio.to_thread(_zip)
        _cleanup_old()
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cleanup_old() -> None:
    backups = sorted(_BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[_MAX_BACKUPS:]:
        try:
            old.unlink()
            meta = old.with_suffix(".meta.json")
            if meta.exists():
                meta.unlink()
        except OSError:
            pass


async def list_backups() -> dict[str, Any]:
    backups: list[dict[str, Any]] = []
    for meta_file in sorted(
        _BACKUP_DIR.glob("*.meta.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:100]:
        try:
            meta = json.loads(meta_file.read_text("utf-8"))
            backups.append(meta)
        except (OSError, json.JSONDecodeError):
            continue
    return {"ok": True, "backups": backups}


def _safe_members(
    archive: zipfile.ZipFile,
    target: Path,
) -> tuple[list[tuple[zipfile.ZipInfo, Path]], list[str]]:
    infos = archive.infolist()
    if len(infos) > _MAX_ARCHIVE_FILES:
        raise ValueError("O backup contém arquivos demais.")
    total_size = sum(max(0, info.file_size) for info in infos)
    if total_size > _MAX_ARCHIVE_BYTES:
        raise ValueError("O backup descompactado excede 2 GB.")

    members: list[tuple[zipfile.ZipInfo, Path]] = []
    conflicts: list[str] = []
    seen: set[str] = set()
    target_resolved = target.resolve()
    for info in infos:
        if info.file_size > _MAX_ARCHIVE_FILE_BYTES:
            raise ValueError(f"Arquivo grande demais no backup: {info.filename}")
        if (
            info.compress_size > 0
            and info.file_size > 10 * 1024 * 1024
            and info.file_size / info.compress_size > 1000
        ):
            raise ValueError(f"Taxa de compressão suspeita em: {info.filename}")

        normalized = info.filename.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if (
            not normalized
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
            or (pure.parts and ":" in pure.parts[0])
        ):
            raise ValueError(f"Caminho inseguro no backup: {info.filename}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise ValueError(f"Links simbólicos não são aceitos no backup: {info.filename}")

        destination = (target_resolved / Path(*pure.parts)).resolve()
        try:
            destination.relative_to(target_resolved)
        except ValueError as exc:
            raise ValueError(f"Caminho fora do destino: {info.filename}") from exc
        collision_key = str(destination).casefold() if os.name == "nt" else str(destination)
        if collision_key in seen:
            raise ValueError(f"Caminho duplicado no backup: {info.filename}")
        seen.add(collision_key)
        if destination.exists() and not info.is_dir():
            conflicts.append(str(destination))
        members.append((info, destination))
    return members, conflicts


async def restore_backup(
    backup_path: str,
    target_dir: str | None = None,
    confirmed: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    path = Path(backup_path).expanduser().resolve()
    if not path.exists() or path.suffix != ".zip":
        return {"ok": False, "error": "Backup não encontrado."}
    if not confirmed:
        return {
            "ok": False,
            "pending_confirmation": True,
            "requires_confirmation": True,
            "risk": "high",
            "backup_path": str(path),
            "target_dir": target_dir,
            "error": "Restaurar um backup altera arquivos e precisa de confirmação.",
        }

    target = (
        Path(target_dir).expanduser().resolve()
        if target_dir
        else path.parent.resolve()
    )

    def _restore() -> dict[str, Any]:
        with zipfile.ZipFile(path, "r") as zf:
            members, conflicts = _safe_members(zf, target)
            if conflicts and not overwrite:
                return {
                    "ok": False,
                    "conflict": True,
                    "requires_overwrite": True,
                    "conflicts": conflicts[:50],
                    "error": "O destino já contém arquivos do backup.",
                }
            target.mkdir(parents=True, exist_ok=True)
            created: list[Path] = []
            try:
                for info, destination in members:
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    mode = "wb" if overwrite else "xb"
                    with zf.open(info, "r") as source, destination.open(mode) as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    created.append(destination)
            except Exception:
                if not overwrite:
                    for created_path in reversed(created):
                        created_path.unlink(missing_ok=True)
                raise
        return {"ok": True, "restored_to": str(target), "files": len(members)}

    try:
        return await asyncio.to_thread(_restore)
    except (zipfile.BadZipFile, ValueError) as exc:
        return {"ok": False, "error": str(exc), "blocked": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
