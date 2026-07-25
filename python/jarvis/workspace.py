"""Safe, workspace-scoped file and developer task operations.

The assistant may only edit files inside a folder explicitly selected by the
user. Paths are resolved against that root and checked again after symlinks are
expanded, which prevents ``../`` escapes and accidental access to the rest of
the computer.
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import minimal_subprocess_env, settings

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TREE_ITEMS = 1500
MAX_SEARCH_RESULTS = 200

IGNORED_NAMES = {
    ".git", ".idea", ".next", ".nuxt", ".parcel-cache", ".pytest_cache",
    ".turbo", ".venv", "__pycache__", "build", "coverage", "dist",
    "node_modules", "release", "target", "venv",
}
SENSITIVE_NAMES = {
    ".aws",
    ".azure",
    ".docker",
    ".env",
    ".envrc",
    ".gcloud",
    ".git-credentials",
    ".gnupg",
    ".htpasswd",
    ".kube",
    ".netrc",
    ".npmrc",
    ".pgpass",
    ".pypirc",
    ".ssh",
    "access_token",
    "api_key",
    "apikey",
    "auth.json",
    "client_secret",
    "credentials",
    "local.settings.json",
    "private_key",
    "refresh_token",
    "secret",
    "secrets",
    "service_account",
    "serviceaccount",
    "serviceaccountkey",
    "token",
    "tokens",
}
SENSITIVE_EXTENSIONS = {
    ".cer",
    ".crt",
    ".der",
    ".jks",
    ".kdbx",
    ".key",
    ".keystore",
    ".mobileprovision",
    ".ovpn",
    ".p12",
    ".p7b",
    ".p7c",
    ".p8",
    ".pem",
    ".pfx",
    ".pk8",
    ".ppk",
}
SENSITIVE_CONFIG_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".enc",
    ".gpg",
    ".ini",
    ".json",
    ".plist",
    ".properties",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SENSITIVE_PARTS = {
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "credentials",
    "firebase_adminsdk",
    "oauth_token",
    "private_key",
    "refresh_token",
    "secret",
    "secrets",
    "service_account",
    "serviceaccount",
    "serviceaccountkey",
    "token",
    "tokens",
}
SENSITIVE_BACKUP_SUFFIXES = {
    ".bak",
    ".backup",
    ".old",
    ".orig",
    ".save",
    ".tmp",
    "~",
}

_STATE_FILE = settings.data_dir / "workspace.json"
_RECENTS_FILE = settings.data_dir / "recent_projects.json"


def _is_sensitive_name(name: str) -> bool:
    """Return whether a single path component commonly stores credentials."""
    low = str(name or "").strip().casefold()
    if not low:
        return False

    # Backups of secret files remain secrets. Strip only well-known wrapper
    # suffixes, then evaluate the original filename below.
    candidate = low
    changed = True
    while changed:
        changed = False
        for suffix in SENSITIVE_BACKUP_SUFFIXES:
            if candidate.endswith(suffix) and len(candidate) > len(suffix):
                candidate = candidate[:-len(suffix)]
                changed = True
                break

    if candidate in SENSITIVE_NAMES or candidate.startswith(".env."):
        return True
    if re.fullmatch(r"id_(?:dsa|ecdsa|ed25519|rsa)(?:\.pub)?", candidate):
        return True

    suffix = Path(candidate).suffix.casefold()
    if suffix in SENSITIVE_EXTENSIONS:
        return True
    if (
        candidate.endswith(".tfstate")
        or ".tfstate." in candidate
        or candidate.endswith(".tfvars")
        or candidate.endswith(".tfvars.json")
        or candidate.endswith(".kubeconfig")
    ):
        return True

    normalized_stem = re.sub(
        r"[^a-z0-9]+",
        "_",
        Path(candidate).stem.casefold(),
    ).strip("_")
    marker_tokens = set(filter(None, normalized_stem.split("_")))
    normalized_markers = {
        marker
        for marker in SENSITIVE_PARTS
        if "_" not in marker
    }
    has_marker = bool(marker_tokens & normalized_markers) or any(
        marker in normalized_stem
        for marker in SENSITIVE_PARTS
        if "_" in marker
    )
    return suffix in SENSITIVE_CONFIG_EXTENSIONS and has_marker


def _is_sensitive(path: Path) -> bool:
    """Apply the sensitive-file policy to a file and all parent components."""
    return any(
        _is_sensitive_name(part)
        for part in Path(path).parts
        if part not in {Path(path).anchor, "/", "\\"}
    )


def _load_root() -> Path | None:
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        root = Path(data["root"]).expanduser().resolve()
        return root if root.is_dir() else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def get_root() -> Path | None:
    return _load_root()


def set_root(value: str) -> dict[str, Any]:
    root = Path(os.path.expandvars(value)).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": "A pasta selecionada não existe."}
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"root": str(root)}, indent=2), encoding="utf-8")
    _remember_root(root)
    return {
        "ok": True,
        "root": str(root),
        "name": root.name,
        "inspection": inspect_root(str(root)),
    }


def _remember_root(root: Path) -> None:
    try:
        existing = json.loads(_RECENTS_FILE.read_text(encoding="utf-8"))
        items = existing if isinstance(existing, list) else []
    except (OSError, json.JSONDecodeError):
        items = []
    now = time.time()
    next_items = [
        {"path": str(root), "name": root.name, "opened_at": now},
        *[item for item in items if item.get("path") != str(root)],
    ][:12]
    _RECENTS_FILE.write_text(
        json.dumps(next_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def recent_projects() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_RECENTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        item for item in raw
        if isinstance(item, dict) and Path(str(item.get("path", ""))).is_dir()
    ][:12]


def _gitignore_patterns(root: Path) -> list[str]:
    target = root / ".gitignore"
    if not target.is_file():
        return []
    try:
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    return [
        line.strip().replace("\\", "/")
        for line in lines
        if line.strip() and not line.lstrip().startswith("!") and not line.lstrip().startswith("#")
    ]


def _ignored(relative: str, patterns: list[str]) -> bool:
    normalized = relative.replace("\\", "/").lstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    for raw in patterns:
        pattern = raw.lstrip("/").rstrip("/")
        if not pattern:
            continue
        if (
            fnmatch.fnmatch(normalized, pattern)
            or fnmatch.fnmatch(name, pattern)
            or ("/" not in pattern and f"/{pattern}/" in f"/{normalized}/")
            or normalized.startswith(f"{pattern}/")
        ):
            return True
    return False


def inspect_root(value: str) -> dict[str, Any]:
    """Return a bounded, content-free project preview before it is opened."""
    root = Path(os.path.expandvars(value)).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": "A pasta selecionada não existe."}
    patterns = _gitignore_patterns(root)
    files = 0
    folders = 0
    total_bytes = 0
    ignored = 0
    truncated = False
    extensions: dict[str, int] = {}
    sensitive: list[str] = []
    names: set[str] = set()
    limit = 25_000
    for current, dirs, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root).as_posix()
        kept_dirs: list[str] = []
        for directory in dirs:
            rel = directory if relative_dir == "." else f"{relative_dir}/{directory}"
            if _is_sensitive(current_path / directory):
                sensitive.append(f"{rel}/")
                ignored += 1
            elif directory in IGNORED_NAMES or _ignored(rel, patterns):
                ignored += 1
            else:
                kept_dirs.append(directory)
                folders += 1
        dirs[:] = kept_dirs
        for filename in filenames:
            rel = filename if relative_dir == "." else f"{relative_dir}/{filename}"
            target = current_path / filename
            if _ignored(rel, patterns):
                ignored += 1
                continue
            files += 1
            names.add(filename.lower())
            if _is_sensitive(target):
                sensitive.append(rel)
            suffix = target.suffix.lower() or "(sem extensão)"
            extensions[suffix] = extensions.get(suffix, 0) + 1
            try:
                total_bytes += target.stat().st_size
            except OSError:
                pass
            if files + folders >= limit:
                truncated = True
                dirs[:] = []
                break
        if truncated:
            break
    frameworks: list[str] = []
    framework_markers = {
        "package.json": "Node.js",
        "vite.config.ts": "Vite",
        "vite.config.js": "Vite",
        "next.config.js": "Next.js",
        "next.config.mjs": "Next.js",
        "electron-builder.json": "Electron",
        "pyproject.toml": "Python",
        "requirements.txt": "Python",
        "cargo.toml": "Rust",
        "go.mod": "Go",
        "composer.json": "PHP",
    }
    for marker, label in framework_markers.items():
        if marker in names and label not in frameworks:
            frameworks.append(label)
    languages = sorted(
        (
            {"extension": extension, "files": count}
            for extension, count in extensions.items()
        ),
        key=lambda item: item["files"],
        reverse=True,
    )[:8]
    return {
        "ok": True,
        "root": str(root),
        "name": root.name,
        "files": files,
        "folders": folders,
        "total_bytes": total_bytes,
        "ignored": ignored,
        "sensitive_count": len(sensitive),
        "sensitive_files": sensitive[:20],
        "frameworks": frameworks,
        "languages": languages,
        "gitignore": bool(patterns),
        "truncated": truncated,
    }


def _require_root() -> Path:
    root = get_root()
    if root is None:
        raise ValueError("Nenhum workspace foi selecionado.")
    return root


def resolve_path(relative_path: str = "") -> Path:
    root = _require_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("O caminho precisa ficar dentro do workspace.") from exc
    return candidate


def relative_path(path: Path) -> str:
    relative = path.resolve().relative_to(_require_root())
    return "" if str(relative) == "." else relative.as_posix()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _language(path: Path) -> str:
    return {
        ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".css": "css",
        ".go": "go", ".html": "html", ".java": "java", ".js": "javascript",
        ".json": "json", ".jsx": "javascript", ".lua": "lua", ".md": "markdown",
        ".php": "php", ".py": "python", ".rb": "ruby", ".rs": "rust",
        ".scss": "scss", ".sh": "shell", ".sql": "sql", ".ts": "typescript",
        ".tsx": "typescript", ".vue": "vue", ".xml": "xml", ".yaml": "yaml",
        ".yml": "yaml",
    }.get(path.suffix.lower(), "plaintext")


def _node(
    path: Path,
    depth: int,
    counter: list[int],
    ignore_patterns: list[str],
) -> dict[str, Any]:
    counter[0] += 1
    result: dict[str, Any] = {
        "name": path.name,
        "path": relative_path(path),
        "is_dir": path.is_dir(),
    }
    if path.is_file():
        try:
            result["size"] = path.stat().st_size
        except OSError:
            result["size"] = None
        return result

    result["children"] = []
    if depth <= 0 or counter[0] >= MAX_TREE_ITEMS:
        result["truncated"] = True
        return result
    try:
        entries = sorted(
            (
                entry for entry in path.iterdir()
                if (
                    entry.name not in IGNORED_NAMES
                    and not _is_sensitive(entry)
                    and not entry.is_symlink()
                    and not _ignored(relative_path(entry), ignore_patterns)
                )
            ),
            key=lambda entry: (not entry.is_dir(), entry.name.lower()),
        )
    except (OSError, PermissionError):
        result["unreadable"] = True
        return result
    for entry in entries:
        if counter[0] >= MAX_TREE_ITEMS:
            result["truncated"] = True
            break
        result["children"].append(_node(entry, depth - 1, counter, ignore_patterns))
    return result


async def tree(depth: int = 5) -> dict[str, Any]:
    root = _require_root()
    counter = [0]
    result = await asyncio.to_thread(
        _node,
        root,
        max(1, min(depth, 8)),
        counter,
        _gitignore_patterns(root),
    )
    return {"ok": True, "root": str(root), "tree": result, "items": counter[0]}


async def read_file(path: str) -> dict[str, Any]:
    target = resolve_path(path)
    if not target.is_file():
        return {"ok": False, "error": "Arquivo não encontrado."}
    if _is_sensitive(target):
        return {"ok": False, "error": "Arquivos sensíveis não são exibidos pelo assistente."}
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        return {"ok": False, "error": "Arquivo maior que 2 MB."}
    raw = await asyncio.to_thread(target.read_bytes)
    if b"\0" in raw[:4096]:
        return {"ok": False, "error": "Arquivos binários não podem ser editados como texto."}
    return {
        "ok": True,
        "path": relative_path(target),
        "content": raw.decode("utf-8", errors="replace"),
        "sha256": _sha(raw),
        "language": _language(target),
        "size": len(raw),
    }


async def write_file(
    path: str,
    content: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    target = resolve_path(path)
    if _is_sensitive(target):
        return {"ok": False, "error": "O assistente não grava arquivos sensíveis."}
    raw = content.encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        return {"ok": False, "error": "Conteúdo maior que 2 MB."}
    if target.exists() and expected_sha256:
        current = await asyncio.to_thread(target.read_bytes)
        if _sha(current) != expected_sha256:
            return {
                "ok": False,
                "conflict": True,
                "error": "O arquivo mudou desde que foi aberto. Recarregue antes de salvar.",
            }

    def _write() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    await asyncio.to_thread(_write)
    return {
        "ok": True,
        "path": relative_path(target),
        "sha256": _sha(raw),
        "size": len(raw),
    }


async def create_entry(path: str, kind: str = "file") -> dict[str, Any]:
    target = resolve_path(path)
    if target.exists():
        return {"ok": False, "error": "Já existe um item com esse nome."}
    if _is_sensitive(target):
        return {"ok": False, "error": "Esse nome é reservado para configuração sensível."}
    if kind == "folder":
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=False)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.touch, exist_ok=False)
    return {"ok": True, "path": relative_path(target), "kind": kind}


async def rename_entry(path: str, destination: str) -> dict[str, Any]:
    source = resolve_path(path)
    target = resolve_path(destination)
    if not source.exists():
        return {"ok": False, "error": "Origem não encontrada."}
    if target.exists():
        return {"ok": False, "error": "O destino já existe."}
    if _is_sensitive(source) or _is_sensitive(target):
        return {"ok": False, "error": "A operação envolve um arquivo sensível."}
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(source.rename, target)
    return {"ok": True, "path": relative_path(target)}


async def delete_entry(path: str, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "requires_confirmation": True, "error": "Confirmação necessária."}
    source = resolve_path(path)
    if not source.exists():
        return {"ok": False, "error": "Item não encontrado."}
    root = _require_root()
    if source == root:
        return {"ok": False, "error": "O workspace inteiro não pode ser removido."}
    if _is_sensitive(source):
        return {"ok": False, "error": "Arquivos sensíveis não podem ser removidos pelo assistente."}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    trash_root = settings.data_dir / "workspace_trash" / stamp
    trash_target = trash_root / relative_path(source)
    trash_target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.move, str(source), str(trash_target))
    return {"ok": True, "deleted": path, "recoverable": True, "trash": str(trash_target)}


async def search(query: str) -> dict[str, Any]:
    root = _require_root()
    needle = query.strip().lower()
    if not needle:
        return {"ok": True, "results": []}

    def _search() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        patterns = _gitignore_patterns(root)
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            dirs[:] = [
                directory for directory in dirs
                if directory not in IGNORED_NAMES
                and not _is_sensitive(current_path / directory)
                and not _ignored(
                    (current_path / directory).relative_to(root).as_posix(),
                    patterns,
                )
            ]
            for name in files:
                target = Path(current) / name
                rel = target.relative_to(root).as_posix()
                if _is_sensitive(target) or _ignored(rel, patterns):
                    continue
                if needle in rel.lower():
                    results.append({"path": rel, "line": None, "preview": "Nome do arquivo"})
                if len(results) >= MAX_SEARCH_RESULTS:
                    return results
                try:
                    if target.stat().st_size > 512 * 1024:
                        continue
                    raw = target.read_bytes()
                    if b"\0" in raw[:4096]:
                        continue
                    for number, line in enumerate(raw.decode("utf-8", errors="ignore").splitlines(), 1):
                        if needle in line.lower():
                            results.append({
                                "path": rel,
                                "line": number,
                                "preview": line.strip()[:180],
                            })
                            if len(results) >= MAX_SEARCH_RESULTS:
                                return results
                except (OSError, PermissionError):
                    continue
        return results

    return {"ok": True, "results": await asyncio.to_thread(_search)}


def available_tasks() -> list[dict[str, str]]:
    root = _require_root()
    tasks: list[dict[str, str]] = [{"id": "git_status", "label": "Git status"}]
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            for script, label in (
                ("lint", "Typecheck / lint"),
                ("test", "Tests"),
                ("build", "Build"),
            ):
                if script in scripts:
                    tasks.append({"id": f"npm_{script}", "label": label})
        except (OSError, ValueError, TypeError):
            pass
    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
        tasks.append({"id": "python_test", "label": "Pytest"})
    return tasks


async def run_task(
    task_id: str,
    on_output: Any | None = None,
    cancel_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    root = _require_root()
    npm = "npm.cmd" if os.name == "nt" else "npm"
    commands: dict[str, list[str]] = {
        "git_status": ["git", "status", "--short", "--branch"],
        "npm_lint": [npm, "run", "lint"],
        "npm_test": [npm, "test"],
        "npm_build": [npm, "run", "build"],
        "python_test": [os.sys.executable, "-m", "pytest", "-q"],
    }
    command = commands.get(task_id)
    if command is None or task_id not in {task["id"] for task in available_tasks()}:
        return {"ok": False, "error": "Tarefa não permitida para este workspace."}
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(root),
            env=minimal_subprocess_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        chunks: list[str] = []

        async def _read() -> None:
            assert process.stdout is not None
            while True:
                if cancel_event and cancel_event.is_set():
                    process.kill()
                    return
                line = await process.stdout.readline()
                if not line:
                    return
                decoded = line.decode("utf-8", errors="replace")
                chunks.append(decoded)
                if on_output:
                    result = on_output(decoded)
                    if asyncio.iscoroutine(result):
                        await result

        await asyncio.wait_for(_read(), timeout=180)
        await process.wait()
        output = "".join(chunks)[-100_000:]
        if cancel_event and cancel_event.is_set():
            return {"ok": False, "cancelled": True, "task": task_id, "output": output}
        return {
            "ok": process.returncode == 0,
            "exit_code": process.returncode,
            "task": task_id,
            "output": output,
        }
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"ok": False, "error": "A tarefa excedeu 3 minutos e foi interrompida."}
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise
    except (OSError, FileNotFoundError) as exc:
        return {"ok": False, "error": str(exc)}
