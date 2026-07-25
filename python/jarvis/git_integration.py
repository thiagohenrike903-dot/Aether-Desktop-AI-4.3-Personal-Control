from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from .config import minimal_subprocess_env

logger = logging.getLogger("jarvis.git")


def _git(*args: str, cwd: str | None = None) -> dict[str, Any]:
    import subprocess
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=minimal_subprocess_env(),
            timeout=60,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": "Git not found. Install git and ensure it's in PATH."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Git command timed out."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def git(*args: str, cwd: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_git, *args, cwd=cwd)


async def status(workspace_root: str) -> dict[str, Any]:
    result = await git("status", "--short", "--branch", cwd=workspace_root)
    if not result.get("ok"):
        return result
    lines = result["stdout"].split("\n")
    branch = ""
    changes: list[dict[str, Any]] = []
    for line in lines:
        if line.startswith("##"):
            branch = line.replace("## ", "").split("...")[0]
        elif line.strip():
            status_flag = line[:2].strip()
            file_path = line[3:].strip()
            changes.append({"status": status_flag, "path": file_path})
    return {
        "ok": True,
        "branch": branch,
        "changes": changes,
        "raw": result["stdout"],
    }


async def log(workspace_root: str, max_count: int = 20) -> dict[str, Any]:
    result = await git(
        "log", f"--max-count={max_count}",
        "--format=%H|%an|%ae|%at|%s",
        cwd=workspace_root,
    )
    if not result.get("ok"):
        return result
    commits: list[dict[str, Any]] = []
    for line in result["stdout"].split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) == 5:
            commits.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "timestamp": int(parts[3]),
                "message": parts[4],
            })
    return {"ok": True, "commits": commits}


async def diff(workspace_root: str, target: str = "HEAD", paths: list[str] | None = None) -> dict[str, Any]:
    args = ["diff", target, "--"]
    if paths:
        args.extend(paths)
    result = await git(*args, cwd=workspace_root)
    if not result.get("ok"):
        return result
    return {"ok": True, "diff": result["stdout"]}


async def add(workspace_root: str, paths: list[str] | None = None) -> dict[str, Any]:
    if paths:
        return await git("add", "--", *paths, cwd=workspace_root)
    return await git("add", "--all", cwd=workspace_root)


async def commit(workspace_root: str, message: str) -> dict[str, Any]:
    add_result = await add(workspace_root)
    if not add_result.get("ok"):
        return add_result
    return await git("commit", "-m", message, cwd=workspace_root)


async def push(workspace_root: str, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    if branch:
        return await git("push", remote, branch, cwd=workspace_root)
    return await git("push", cwd=workspace_root)


async def pull(workspace_root: str, remote: str = "origin", branch: str | None = None) -> dict[str, Any]:
    if branch:
        return await git("pull", remote, branch, cwd=workspace_root)
    return await git("pull", cwd=workspace_root)


async def branch_list(workspace_root: str) -> dict[str, Any]:
    result = await git("branch", "-a", cwd=workspace_root)
    if not result.get("ok"):
        return result
    branches: list[dict[str, Any]] = []
    for line in result["stdout"].split("\n"):
        line = line.strip()
        if not line:
            continue
        is_current = line.startswith("*")
        name = line.lstrip("*").strip()
        branches.append({"name": name, "current": is_current})
    return {"ok": True, "branches": branches}


async def branch_create(workspace_root: str, name: str, base: str | None = None) -> dict[str, Any]:
    if base:
        return await git("checkout", "-b", name, base, cwd=workspace_root)
    return await git("checkout", "-b", name, cwd=workspace_root)


async def branch_checkout(workspace_root: str, name: str) -> dict[str, Any]:
    return await git("checkout", name, cwd=workspace_root)


async def merge(workspace_root: str, branch: str) -> dict[str, Any]:
    return await git("merge", branch, cwd=workspace_root)


async def stash(workspace_root: str) -> dict[str, Any]:
    return await git("stash", cwd=workspace_root)


async def stash_pop(workspace_root: str) -> dict[str, Any]:
    return await git("stash", "pop", cwd=workspace_root)
