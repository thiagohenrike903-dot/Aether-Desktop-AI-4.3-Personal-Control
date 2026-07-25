"""Review-first AI coding planner for the selected workspace.

The model never writes directly to disk. It returns a structured plan with
complete file contents, the UI shows the proposed changes, and only an explicit
Apply action commits the plan.
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings
from . import skills, workspace
from .llm_providers import get_provider, build_system_prompt

_PLANS: dict[str, dict[str, Any]] = {}
_PLAN_TTL_SECONDS = 30 * 60
_CHECKPOINT_DIR = settings.data_dir / "checkpoints"
_HISTORY_FILE = settings.data_dir / "code_history.json"

logger = logging.getLogger("jarvis.code_agent")


async def _emit(callback: Any | None, event: str, label: str, progress: int, detail: str = "") -> None:
    if not callback:
        return
    result = callback({
        "type": event,
        "label": label,
        "progress": progress,
        "detail": detail,
    })
    if hasattr(result, "__await__"):
        await result


def _load_history() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_history(items: list[dict[str, Any]]) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(
        json.dumps(items[:100], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _mark_history(checkpoint_id: str, status: str) -> None:
    items = _load_history()
    for entry in items:
        if entry.get("id") == checkpoint_id:
            entry["status"] = status
            entry[f"{status}_at"] = time.time()
            break
    _save_history(items)


def history() -> list[dict[str, Any]]:
    return _load_history()


def _workspace_matches(expected_root: str) -> bool:
    current = workspace.get_root()
    return bool(
        current is not None
        and str(current.resolve()) == str(Path(expected_root).resolve())
    )


def _checkpoint_backup_path(checkpoint_path: Path, relative_path: str) -> Path:
    """Resolve a checkpoint payload path without allowing absolute-path escapes."""
    files_root = (checkpoint_path / "files").resolve()
    backup = (files_root / relative_path).resolve()
    try:
        backup.relative_to(files_root)
    except ValueError as exc:
        raise RuntimeError("O checkpoint contém um caminho de backup inválido.") from exc
    return backup


async def _create_checkpoint(
    changes: list[dict[str, Any]],
    summary: str,
    expected_root: str | None = None,
) -> str:
    current_root = workspace.get_root()
    if current_root is None:
        raise RuntimeError("Nenhum workspace foi selecionado.")
    if expected_root and not _workspace_matches(expected_root):
        raise RuntimeError("O workspace mudou antes da criação do checkpoint.")
    checkpoint_id = str(uuid.uuid4())
    checkpoint_path = _CHECKPOINT_DIR / checkpoint_id
    checkpoint_path.mkdir(parents=True, exist_ok=False)
    manifest: list[dict[str, Any]] = []
    for change in changes:
        if expected_root and not _workspace_matches(expected_root):
            raise RuntimeError("O workspace mudou durante a criação do checkpoint.")
        target = workspace.resolve_path(change["path"])
        relative = workspace.relative_path(target)
        if not relative:
            raise RuntimeError("Não é possível criar checkpoint da raiz do workspace.")
        entry: dict[str, Any] = {
            "path": relative,
            "existed": target.is_file(),
        }
        if target.is_file():
            current = await workspace.read_file(relative)
            if not current.get("ok"):
                raise RuntimeError(current.get("error", f"Falha ao criar checkpoint de {relative}."))
            backup = _checkpoint_backup_path(checkpoint_path, relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(current["content"], encoding="utf-8")
        manifest.append(entry)
    created_at = time.time()
    (checkpoint_path / "manifest.json").write_text(
        json.dumps(
            {
                "id": checkpoint_id,
                "summary": summary,
                "created_at": created_at,
                "workspace_root": str(current_root.resolve()),
                "files": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    items = [
        {
            "id": checkpoint_id,
            "summary": summary,
            "created_at": created_at,
            "workspace_root": str(current_root.resolve()),
            "files": [item["path"] for item in manifest],
            "status": "applied",
        },
        *_load_history(),
    ]
    _save_history(items)
    return checkpoint_id


async def undo(checkpoint_id: str, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        return {"ok": False, "requires_confirmation": True}
    checkpoint_root = _CHECKPOINT_DIR.resolve()
    checkpoint_path = (checkpoint_root / checkpoint_id).resolve()
    try:
        checkpoint_path.relative_to(checkpoint_root)
    except ValueError:
        return {"ok": False, "error": "Identificador de checkpoint inválido.", "blocked": True}
    try:
        manifest = json.loads((checkpoint_path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "Checkpoint não encontrado."}
    expected_root = str(manifest.get("workspace_root") or "")
    if expected_root and not _workspace_matches(expected_root):
        return {
            "ok": False,
            "workspace_mismatch": True,
            "error": "Selecione o workspace original antes de desfazer este checkpoint.",
        }
    raw_files = manifest.get("files", [])
    if not isinstance(raw_files, list):
        return {"ok": False, "error": "Manifesto de checkpoint inválido.", "blocked": True}
    prepared: list[tuple[dict[str, Any], str, Path, Path]] = []
    seen: set[str] = set()
    try:
        for item in raw_files:
            if not isinstance(item, dict):
                raise RuntimeError("Manifesto de checkpoint inválido.")
            target = workspace.resolve_path(str(item.get("path", "")))
            relative = workspace.relative_path(target)
            if not relative or relative in seen:
                raise RuntimeError("Manifesto de checkpoint contém caminhos inválidos ou duplicados.")
            seen.add(relative)
            backup = _checkpoint_backup_path(checkpoint_path, relative)
            if item.get("existed") and not backup.is_file():
                raise RuntimeError(f"Backup ausente para {relative}.")
            prepared.append((item, relative, target, backup))
    except (OSError, RuntimeError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "blocked": True}

    restored: list[str] = []
    for item, relative, target, backup in reversed(prepared):
        if expected_root and not _workspace_matches(expected_root):
            return {
                "ok": False,
                "workspace_mismatch": True,
                "error": "O workspace mudou durante a restauração.",
            }
        if item.get("existed"):
            result = await workspace.write_file(relative, backup.read_text(encoding="utf-8"))
            if not result.get("ok"):
                return result
        elif target.exists():
            if target.is_dir():
                return {"ok": False, "error": f"Não é seguro desfazer a pasta {relative} automaticamente."}
            target.unlink()
        restored.append(relative)
    items = _load_history()
    for entry in items:
        if entry.get("id") == checkpoint_id:
            entry["status"] = "undone"
            entry["undone_at"] = time.time()
    _save_history(items)
    return {"ok": True, "restored": restored, "checkpoint_id": checkpoint_id}


def _clean_old_plans() -> None:
    cutoff = time.time() - _PLAN_TTL_SECONDS
    for plan_id in [key for key, value in _PLANS.items() if value["created_at"] < cutoff]:
        _PLANS.pop(plan_id, None)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("O modelo não retornou um plano JSON válido.")
    return json.loads(cleaned[start:end + 1])


async def _context_files(paths: list[str]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    total = 0
    for path in paths[:16]:
        result = await workspace.read_file(path)
        if not result.get("ok"):
            continue
        content = result["content"]
        if total + len(content) > 180_000:
            break
        total += len(content)
        selected.append({"path": result["path"], "content": content})
    return selected


async def plan(
    instruction: str,
    paths: list[str],
    progress: Any | None = None,
) -> dict[str, Any]:
    _clean_old_plans()
    await _emit(progress, "analysis", "Analisando a solicitação", 6)
    provider = get_provider()
    if provider is None:
        return {
            "ok": False,
            "error": "Nenhum provedor de IA configurado. Configure GEMINI_API_KEY ou LLM_API_KEY no .env.",
            "configuration_required": True,
        }
    root = workspace.get_root()
    if root is None:
        return {"ok": False, "error": "Selecione um workspace primeiro."}
    await _emit(progress, "workspace", "Lendo a estrutura do projeto", 16, root.name)
    tree = await workspace.tree(depth=5)
    await _emit(progress, "files", "Lendo arquivos relevantes", 28, f"{len(paths[:16])} arquivo(s) selecionado(s)")
    files = await _context_files(paths)
    active_skills = skills.match_skills(instruction, str(root))
    knowledge_paths = list(dict.fromkeys(
        path
        for item in active_skills
        for path in item.get("knowledge_files", [])
    ))
    skill_knowledge = await _context_files(knowledge_paths[:12])
    prompt = {
        "instruction": instruction.strip(),
        "workspace_tree": tree["tree"],
        "open_files": files,
        "active_skills": [
            {
                "name": item["name"],
                "instructions": item["instructions"],
                "rules": item["rules"],
                "examples": item["examples"],
                "priority": item["priority"],
            }
            for item in active_skills
        ],
        "skill_knowledge": skill_knowledge,
    }
    await _emit(
        progress,
        "skills",
        "Aplicando contexto e skills",
        38,
        ", ".join(item["name"] for item in active_skills) or "Nenhuma skill específica ativada",
    )
    await _emit(progress, "model", "Gerando uma proposta revisável", 48, settings.agent_orchestrator_model)

    system = (
        "Você é um engenheiro de software sênior trabalhando em um workspace local.\n"
        "Crie um plano mínimo e correto para atender ao pedido. Não invente arquivos\n"
        "que não sejam necessários. Preserve o estilo do projeto. Nunca toque em .env,\n"
        "credenciais, node_modules, builds ou arquivos binários.\n\n"
        "Retorne SOMENTE JSON, sem formatação markdown:\n"
        '{\n'
        '  "summary": "resumo curto em português",\n'
        '  "notes": ["observação"],\n'
        '  "changes": [\n'
        '    {\n'
        '      "operation": "write|create|delete",\n'
        '      "path": "caminho/relativo",\n'
        '      "content": "conteúdo COMPLETO para write/create; vazio em delete",\n'
        '      "explanation": "por que"\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "Use delete apenas quando indispensável. O conteúdo precisa ser o arquivo\n"
        "completo, nunca um diff parcial. Não execute comandos."
    ).strip()

    user_content = json.dumps(prompt, ensure_ascii=False)
    contents = [{"role": "user", "parts": [{"text": user_content}]}]

    try:
        text = await provider.respond(
            system=system,
            contents=contents,
            temperature=0.2,
            max_tokens=65536,
        )
        if not text:
            return {"ok": False, "error": "O modelo não retornou conteúdo."}
        model_plan = _extract_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"Não foi possível gerar o plano: {exc}"}

    await _emit(progress, "diff", "Validando caminhos e preparando diffs", 78)
    proposed: list[dict[str, Any]] = []
    for raw_change in model_plan.get("changes", [])[:30]:
        operation = str(raw_change.get("operation", "")).lower()
        path = str(raw_change.get("path", "")).replace("\\", "/").lstrip("/")
        if operation not in {"write", "create", "delete"} or not path:
            continue
        try:
            target = workspace.resolve_path(path)
        except ValueError:
            continue
        path = workspace.relative_path(target)
        if not path:
            continue
        if workspace._is_sensitive(target):  # shared security policy
            continue
        if target.exists() and target.is_dir():
            continue
        old = ""
        old_sha = None
        if target.is_file():
            current = await workspace.read_file(path)
            if current.get("ok"):
                old = current["content"]
                old_sha = current["sha256"]
        content = "" if operation == "delete" else str(raw_change.get("content", ""))
        if operation == "write" and not target.exists():
            operation = "create"
        if operation == "create" and target.exists():
            operation = "write"
        diff = "\n".join(difflib.unified_diff(
            old.splitlines(),
            content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=3,
        ))
        proposed.append({
            "operation": operation,
            "path": path,
            "content": content,
            "old_sha256": old_sha,
            "explanation": str(raw_change.get("explanation", "")),
            "diff": diff[:80_000],
            "additions": sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")),
            "deletions": sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")),
        })

    if not proposed:
        return {"ok": False, "error": "O modelo não propôs alterações aplicáveis."}
    plan_id = str(uuid.uuid4())
    stored = {
        "id": plan_id,
        "created_at": time.time(),
        "workspace_root": str(root.resolve()),
        "summary": str(model_plan.get("summary", "Alterações propostas")),
        "notes": [str(note) for note in model_plan.get("notes", [])[:10]],
        "changes": proposed,
    }
    _PLANS[plan_id] = stored
    await _emit(progress, "review", "Proposta pronta para revisão", 100, f"{len(proposed)} arquivo(s)")
    return {
        "ok": True,
        "plan_id": plan_id,
        "summary": stored["summary"],
        "notes": stored["notes"],
        "used_skills": [
            {"id": item["id"], "name": item["name"], "version": item["version"]}
            for item in active_skills
        ],
        "changes": [
            {key: value for key, value in change.items() if key != "content"}
            for change in proposed
        ],
    }


async def apply(
    plan_id: str,
    confirmed: bool = False,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    _clean_old_plans()
    plan_data = _PLANS.get(plan_id)
    if plan_data is None:
        return {"ok": False, "error": "O plano expirou. Gere uma nova proposta."}
    if not confirmed:
        return {"ok": False, "requires_confirmation": True, "error": "Confirme as alterações."}
    expected_root = str(plan_data.get("workspace_root") or "")
    if expected_root and not _workspace_matches(expected_root):
        return {
            "ok": False,
            "workspace_mismatch": True,
            "error": "O plano pertence a outro workspace. Reabra o projeto original.",
        }

    selected = (
        [change for change in plan_data["changes"] if change["path"] in set(paths)]
        if paths is not None
        else list(plan_data["changes"])
    )
    if not selected:
        return {"ok": False, "error": "Selecione ao menos uma alteração para aplicar."}
    for change in selected:
        target = workspace.resolve_path(change["path"])
        if change["operation"] == "create" and target.exists():
            return {
                "ok": False,
                "conflict": True,
                "error": f"Conflito: {change['path']} foi criado depois que o plano foi gerado.",
            }
        if not change.get("old_sha256"):
            continue
        current = await workspace.read_file(change["path"])
        if not current.get("ok") or current.get("sha256") != change["old_sha256"]:
            return {
                "ok": False,
                "conflict": True,
                "error": f"Conflito: {change['path']} mudou depois que o plano foi criado.",
            }
    checkpoint_id = await _create_checkpoint(
        selected,
        plan_data["summary"],
        expected_root or None,
    )
    backups: list[dict[str, Any]] = []
    applied: list[str] = []
    try:
        for change in selected:
            if expected_root and not _workspace_matches(expected_root):
                raise RuntimeError("O workspace mudou durante a aplicação do plano.")
            path = change["path"]
            target = workspace.resolve_path(path)
            existed = target.exists()
            old_content = None
            if target.is_file():
                current = await workspace.read_file(path)
                if not current.get("ok"):
                    raise RuntimeError(current.get("error", f"Não foi possível ler {path}."))
                if change.get("old_sha256") and current["sha256"] != change["old_sha256"]:
                    raise RuntimeError(f"Conflito: {path} mudou depois que o plano foi criado.")
                old_content = current["content"]
            backups.append({"path": path, "existed": existed, "content": old_content})
            if change["operation"] == "delete":
                result = await workspace.delete_entry(path, confirmed=True)
            else:
                result = await workspace.write_file(
                    path,
                    change["content"],
                    expected_sha256=change.get("old_sha256"),
                )
            if not result.get("ok"):
                raise RuntimeError(result.get("error", f"Falha em {path}."))
            applied.append(path)
    except Exception as exc:
        for backup in reversed(backups):
            try:
                target = workspace.resolve_path(backup["path"])
                if backup["existed"] and backup["content"] is not None:
                    await workspace.write_file(backup["path"], backup["content"])
                elif not backup["existed"] and target.exists():
                    if target.is_dir():
                        target.rmdir()
                    else:
                        target.unlink()
            except Exception:
                pass
        _mark_history(checkpoint_id, "rolled_back")
        return {"ok": False, "error": str(exc), "rolled_back": True, "applied_before_error": applied}
    _PLANS.pop(plan_id, None)
    return {
        "ok": True,
        "applied": applied,
        "rejected": [
            change["path"] for change in plan_data["changes"]
            if change["path"] not in set(applied)
        ],
        "summary": plan_data["summary"],
        "checkpoint_id": checkpoint_id,
    }


def discard(plan_id: str) -> dict[str, Any]:
    existed = _PLANS.pop(plan_id, None) is not None
    return {"ok": existed, "discarded": plan_id if existed else None}
