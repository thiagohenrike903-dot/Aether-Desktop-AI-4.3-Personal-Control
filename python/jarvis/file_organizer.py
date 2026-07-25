"""File organizer — sorts messy folders into clean category-based structures.

Capabilities:
  - Organize Downloads by file type (Documents, Images, Videos, Music, Archives, etc.)
  - Organize by date (year/month)
  - Dry-run mode to preview before moving
  - Safe operations with undo capability
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.file_organizer")

# Category definitions: extension -> folder name
FILE_CATEGORIES: dict[str, str] = {
    # Documents
    ".pdf": "Documentos", ".doc": "Documentos", ".docx": "Documentos",
    ".ppt": "Documentos", ".pptx": "Documentos", ".odt": "Documentos",
    ".odp": "Documentos", ".rtf": "Documentos", ".tex": "Documentos",
    ".xls": "Planilhas", ".xlsx": "Planilhas", ".ods": "Planilhas",
    ".csv": "Planilhas", ".tsv": "Planilhas",
    # Text
    ".txt": "Textos", ".md": "Textos", ".log": "Textos",
    # Images
    ".jpg": "Imagens", ".jpeg": "Imagens", ".png": "Imagens",
    ".gif": "Imagens", ".bmp": "Imagens", ".svg": "Imagens",
    ".webp": "Imagens", ".ico": "Imagens", ".tiff": "Imagens",
    ".raw": "Imagens", ".psd": "Imagens", ".ai": "Imagens",
    # Videos
    ".mp4": "Vídeos", ".avi": "Vídeos", ".mkv": "Vídeos",
    ".mov": "Vídeos", ".wmv": "Vídeos", ".flv": "Vídeos",
    ".webm": "Vídeos", ".m4v": "Vídeos",
    # Music / Audio
    ".mp3": "Música", ".wav": "Música", ".flac": "Música",
    ".aac": "Música", ".ogg": "Música", ".wma": "Música",
    ".m4a": "Música",
    # Archives
    ".zip": "Arquivos", ".rar": "Arquivos", ".7z": "Arquivos",
    ".tar": "Arquivos", ".gz": "Arquivos", ".bz2": "Arquivos",
    ".xz": "Arquivos", ".iso": "Arquivos",
    # Code
    ".py": "Código", ".js": "Código", ".ts": "Código",
    ".tsx": "Código", ".jsx": "Código", ".html": "Código",
    ".css": "Código", ".scss": "Código", ".less": "Código",
    ".json": "Código", ".xml": "Código", ".yaml": "Código",
    ".yml": "Código", ".toml": "Código", ".ini": "Código",
    ".cfg": "Código", ".sh": "Código", ".bat": "Código",
    ".ps1": "Código", ".sql": "Código", ".rb": "Código",
    ".go": "Código", ".rs": "Código", ".java": "Código",
    ".cpp": "Código", ".c": "Código", ".h": "Código",
    ".swift": "Código", ".kt": "Código",
    # Executables
    ".exe": "Executáveis", ".msi": "Executáveis",
    ".apk": "Executáveis", ".appimage": "Executáveis",
    ".dmg": "Executáveis", ".deb": "Executáveis",
    ".rpm": "Executáveis",
    # Torrents
    ".torrent": "Torrents",
    # Fonts
    ".ttf": "Fontes", ".otf": "Fontes", ".woff": "Fontes",
    ".woff2": "Fontes", ".eot": "Fontes",
    # Subtitles
    ".srt": "Legendas", ".vtt": "Legendas",
    # Shortcuts
    ".lnk": "Atalhos", ".url": "Atalhos",
    # 3D / CAD
    ".stl": "3D", ".obj": "3D", ".fbx": "3D",
    ".blend": "3D", ".step": "3D",
}

# Files/folders that should never be moved
EXCLUDED_NAMES = {
    "desktop.ini", "thumbs.db", ".ds_store",
    "node_modules", "venv", ".venv", "__pycache__",
}


def categorize_file(filename: str) -> str | None:
    """Return the category folder name for a file, or None if unknown."""
    ext = Path(filename).suffix.lower()
    return FILE_CATEGORIES.get(ext)


def _plan_organization(
    folder_path: Path,
    by_type: bool = True,
    by_date: bool = False,
    dry_run: bool = True,
) -> list[dict[str, Any]]:
    """Analyze a folder and plan file organization.

    Returns a list of move operations with source, destination, and category.
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return [{"ok": False, "error": f"Folder not found: {folder_path}"}]

    moves: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    stats = {"total": 0, "organized": 0, "skipped": 0, "errors": 0}

    try:
        entries = sorted(folder_path.iterdir(), key=lambda e: e.name.lower())
    except PermissionError as exc:
        return [{"ok": False, "error": f"Permission denied: {exc}"}]

    for entry in entries:
        if entry.name.lower() in EXCLUDED_NAMES:
            skipped.append({"name": entry.name, "reason": "excluded name"})
            stats["skipped"] += 1
            continue
        if entry.name.startswith("."):
            skipped.append({"name": entry.name, "reason": "hidden file"})
            stats["skipped"] += 1
            continue

        stats["total"] += 1

        if entry.is_dir():
            skipped.append({"name": entry.name, "reason": "is a directory"})
            stats["skipped"] += 1
            continue

        category = categorize_file(entry.name)
        if not category:
            skipped.append({"name": entry.name, "reason": "unknown type"})
            stats["skipped"] += 1
            continue

        dest_dir = folder_path / category
        dest_path = dest_dir / entry.name

        # Handle name conflicts
        if dest_path.exists():
            stem = entry.stem
            suffix = entry.suffix
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        moves.append({
            "source": str(entry),
            "destination": str(dest_path),
            "category": category,
            "size": entry.stat().st_size,
            "name": entry.name,
        })
        stats["organized"] += 1

    if by_date and moves:
        # Organize files within each category by date (year/month)
        date_moves: list[dict[str, Any]] = []
        for move in moves:
            src = Path(move["source"])
            mtime = src.stat().st_mtime
            year = time.strftime("%Y", time.localtime(mtime))
            month = time.strftime("%m-%B", time.localtime(mtime))
            category_dir = folder_path / move["category"]
            date_dir = category_dir / year / month
            dest = date_dir / src.name
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                counter = 1
                while dest.exists():
                    dest = date_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            move["destination"] = str(dest)
            date_moves.append(move)
        moves = date_moves

    return {
        "ok": True,
        "folder": str(folder_path),
        "stats": stats,
        "moves": moves,
        "skipped": skipped,
        "errors": errors,
        "by_type": by_type,
        "by_date": by_date,
        "dry_run": dry_run,
        "categories": sorted({m["category"] for m in moves}),
    }


def _execute_moves(moves: list[dict[str, Any]], undo_log: Path) -> list[dict[str, Any]]:
    """Execute the planned file moves and log them for undo."""
    results: list[dict[str, Any]] = []
    undo_entries: list[dict[str, Any]] = []

    for move in moves:
        src = Path(move["source"])
        dst = Path(move["destination"])
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            results.append({
                "ok": True,
                "source": move["source"],
                "destination": str(dst),
                "name": move["name"],
                "category": move["category"],
            })
            undo_entries.append({
                "source": str(dst),
                "destination": move["source"],
            })
        except Exception as exc:
            results.append({
                "ok": False,
                "source": move["source"],
                "error": str(exc),
            })

    if undo_entries:
        try:
            existing = []
            if undo_log.exists():
                existing = json.loads(undo_log.read_text(encoding="utf-8"))
            existing.append({
                "ts": time.time(),
                "entries": undo_entries,
            })
            undo_log.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("Failed to write undo log: %s", exc)

    return results


async def organize_folder(
    folder_path: str,
    by_type: bool = True,
    by_date: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Organize files in a folder by category (and optionally by date).

    When dry_run=True, only plans and returns the moves without executing.
    """
    path = Path(os.path.expandvars(os.path.expanduser(folder_path)))

    plan = _plan_organization(path, by_type=by_date or by_type, by_date=by_date, dry_run=dry_run)
    if not plan.get("ok"):
        return plan

    if dry_run:
        return plan

    undo_log = path / ".aether_organize_undo.json"
    moves = plan["moves"]

    results = await asyncio.to_thread(_execute_moves, moves, undo_log)

    executed = sum(1 for r in results if r.get("ok"))
    failed = sum(1 for r in results if not r.get("ok"))

    return {
        "ok": True,
        "folder": str(path),
        "dry_run": False,
        "stats": {
            "planned": len(moves),
            "executed": executed,
            "failed": failed,
        },
        "results": results,
        "categories": plan["categories"],
        "undo_log": str(undo_log),
    }


async def undo_last_organization(folder_path: str) -> dict[str, Any]:
    """Undo the last organization operation in a folder."""
    path = Path(os.path.expandvars(os.path.expanduser(folder_path)))
    undo_log = path / ".aether_organize_undo.json"

    if not undo_log.exists():
        return {"ok": False, "error": "Nenhuma operação anterior para desfazer."}

    try:
        entries = json.loads(undo_log.read_text(encoding="utf-8"))
        if not entries:
            return {"ok": False, "error": "Nenhuma operação anterior para desfazer."}

        last = entries.pop()
        undo_entries = last["entries"]

        # Reverse the moves
        restored = 0
        for entry in reversed(undo_entries):
            src = Path(entry["source"])
            dst = Path(entry["destination"])
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.move(str(src), str(dst))
                    restored += 1
            except Exception as exc:
                log.warning("Undo failed for %s: %s", src, exc)

        # Update undo log
        if entries:
            undo_log.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            undo_log.unlink(missing_ok=True)

        return {
            "ok": True,
            "restored": restored,
            "total": len(undo_entries),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def clean_temp_files(
    folder_path: str,
    days_old: int = 30,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Find and optionally delete temporary/old files.

    Targets: .tmp, .temp, .cache files, and files in known temp directories
    that haven't been modified in `days_old` days.
    """
    path = Path(os.path.expandvars(os.path.expanduser(folder_path)))
    if not path.exists() or not path.is_dir():
        return {"ok": False, "error": f"Folder not found: {path}"}

    TEMP_EXTS = {".tmp", ".temp", ".bak", ".swp", ".cache", ".log"}
    cutoff = time.time() - (days_old * 86400)

    candidates: list[dict[str, Any]] = []
    total_size = 0

    for entry in path.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() in TEMP_EXTS:
            try:
                mtime = entry.stat().st_mtime
                if mtime < cutoff:
                    size = entry.stat().st_size
                    candidates.append({
                        "name": entry.name,
                        "path": str(entry),
                        "size": size,
                        "last_modified": time.ctime(mtime),
                    })
                    total_size += size
            except (PermissionError, OSError):
                continue

    if dry_run:
        return {
            "ok": True,
            "folder": str(path),
            "dry_run": True,
            "candidates": candidates,
            "total_files": len(candidates),
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    # Actually delete
    deleted = 0
    freed = 0
    for c in candidates:
        try:
            Path(c["path"]).unlink()
            deleted += 1
            freed += c["size"]
        except Exception as exc:
            log.warning("Failed to delete %s: %s", c["path"], exc)

    return {
        "ok": True,
        "folder": str(path),
        "dry_run": False,
        "deleted": deleted,
        "total_files": len(candidates),
        "freed": freed,
        "freed_mb": round(freed / (1024 * 1024), 2),
    }
