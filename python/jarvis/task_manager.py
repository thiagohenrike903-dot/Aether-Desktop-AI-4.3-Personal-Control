"""Observable background jobs for coding and project validation."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from . import code_agent, workspace
from .config import settings

_TASKS: dict[str, dict[str, Any]] = {}
_ARCHIVE_FILE = settings.data_dir / "tasks.json"
_QUEUE_LOCK: asyncio.Lock | None = None


def _queue_lock() -> asyncio.Lock:
    global _QUEUE_LOCK
    if _QUEUE_LOCK is None:
        _QUEUE_LOCK = asyncio.Lock()
    return _QUEUE_LOCK


def _event(
    task: dict[str, Any],
    event_type: str,
    label: str,
    *,
    progress: int | None = None,
    detail: str = "",
) -> None:
    task["event_counter"] += 1
    item = {
        "id": task["event_counter"],
        "ts": time.time(),
        "type": event_type,
        "label": label,
        "detail": detail,
    }
    if progress is not None:
        task["progress"] = max(0, min(100, progress))
        item["progress"] = task["progress"]
    task["events"].append(item)
    task["events"] = task["events"][-600:]
    task["updated_at"] = time.time()
    _persist()


def _public(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in task.items()
        if not key.startswith("_")
    }


def _persist() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    snapshots = [_public(task) for task in sorted(
        _TASKS.values(),
        key=lambda item: item["created_at"],
        reverse=True,
    )[:50]]
    _ARCHIVE_FILE.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_archived() -> None:
    try:
        items = json.loads(_ARCHIVE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(items, list):
        return
    for raw in items[:50]:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        task = dict(raw)
        task.setdefault("events", [])
        task.setdefault("event_counter", max(
            (int(event.get("id", 0)) for event in task["events"] if isinstance(event, dict)),
            default=0,
        ))
        task["_resume"] = asyncio.Event()
        task["_resume"].set()
        task["_cancel"] = asyncio.Event()
        task["_runner"] = None
        if task.get("status") in {"queued", "running", "paused", "applying", "awaiting_review"}:
            task["status"] = "failed"
            task["error"] = "A tarefa foi interrompida pelo fechamento do aplicativo."
            task["event_counter"] += 1
            task["events"].append({
                "id": task["event_counter"],
                "ts": time.time(),
                "type": "error",
                "label": "Execução interrompida",
                "detail": task["error"],
            })
        _TASKS[str(task["id"])] = task


def _new(kind: str, title: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "kind": kind,
        "title": title,
        "status": "queued",
        "progress": 0,
        "payload": payload,
        "events": [],
        "event_counter": 0,
        "result": None,
        "error": None,
        "plan_id": None,
        "created_at": now,
        "updated_at": now,
        "_resume": asyncio.Event(),
        "_cancel": asyncio.Event(),
        "_runner": None,
    }
    task["_resume"].set()
    _TASKS[task_id] = task
    _event(task, "queued", "Tarefa adicionada à fila", progress=0)
    return task


async def _checkpoint(task: dict[str, Any]) -> None:
    if task["_cancel"].is_set():
        raise asyncio.CancelledError
    await task["_resume"].wait()
    if task["_cancel"].is_set():
        raise asyncio.CancelledError


async def _run_code(task: dict[str, Any]) -> None:
    try:
        async with _queue_lock():
            await _checkpoint(task)
            task["status"] = "running"
            _event(task, "started", "Execução iniciada", progress=2)

            async def progress(event: dict[str, Any]) -> None:
                await _checkpoint(task)
                _event(
                    task,
                    str(event.get("type", "activity")),
                    str(event.get("label", "Atividade")),
                    progress=int(event.get("progress", task["progress"])),
                    detail=str(event.get("detail", "")),
                )

            result = await code_agent.plan(
                str(task["payload"].get("instruction", "")),
                list(task["payload"].get("paths", [])),
                progress=progress,
            )
            await _checkpoint(task)
            task["result"] = result
            if result.get("ok"):
                task["status"] = "awaiting_review"
                task["plan_id"] = result.get("plan_id")
                task["progress"] = 100
            else:
                task["status"] = "failed"
                task["error"] = result.get("error", "Não foi possível gerar a proposta.")
                _event(task, "error", "A execução falhou", detail=task["error"])
    except asyncio.CancelledError:
        task["status"] = "cancelled"
        _event(task, "cancelled", "Execução cancelada", detail="Nenhuma alteração foi aplicada.")
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)
        _event(task, "error", "Erro inesperado", detail=str(exc))
    finally:
        task["updated_at"] = time.time()
        _persist()


async def _run_validation(task: dict[str, Any]) -> None:
    try:
        async with _queue_lock():
            await _checkpoint(task)
            task["status"] = "running"
            _event(task, "started", "Validação iniciada", progress=5)
            line_count = 0

            async def output(line: str) -> None:
                nonlocal line_count
                line_count += 1
                _event(
                    task,
                    "output",
                    "Saída do terminal",
                    progress=min(92, 8 + line_count),
                    detail=line.rstrip()[:4000],
                )

            result = await workspace.run_task(
                str(task["payload"].get("task_id", "")),
                on_output=output,
                cancel_event=task["_cancel"],
            )
            task["result"] = result
            if result.get("cancelled"):
                task["status"] = "cancelled"
                _event(task, "cancelled", "Comando cancelado")
            elif result.get("ok"):
                task["status"] = "completed"
                _event(task, "success", "Validação concluída", progress=100)
            else:
                task["status"] = "failed"
                task["error"] = result.get("error") or "O comando terminou com erros."
                _event(
                    task,
                    "error",
                    "Validação encontrou erros",
                    progress=100,
                    detail=task["error"],
                )
    except asyncio.CancelledError:
        task["_cancel"].set()
        task["status"] = "cancelled"
        _event(task, "cancelled", "Comando cancelado")
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)
        _event(task, "error", "Erro inesperado", detail=str(exc))
    finally:
        task["updated_at"] = time.time()
        _persist()


def create_code_task(
    instruction: str,
    paths: list[str],
    session_id: str,
) -> dict[str, Any]:
    instruction = instruction.strip()
    if not instruction:
        raise ValueError("Descreva o que deve ser implementado.")
    task = _new(
        "code",
        instruction[:90],
        {"instruction": instruction, "paths": paths[:16], "session_id": session_id},
    )
    task["_runner"] = asyncio.create_task(_run_code(task))
    return _public(task)


def create_validation_task(task_id: str) -> dict[str, Any]:
    allowed = {item["id"] for item in workspace.available_tasks()}
    if task_id not in allowed:
        raise ValueError("Essa validação não está disponível no projeto.")
    labels = {item["id"]: item["label"] for item in workspace.available_tasks()}
    task = _new("validation", labels.get(task_id, task_id), {"task_id": task_id})
    task["_runner"] = asyncio.create_task(_run_validation(task))
    return _public(task)


def get_task(task_id: str) -> dict[str, Any] | None:
    task = _TASKS.get(task_id)
    return _public(task) if task else None


def list_tasks(limit: int = 30) -> list[dict[str, Any]]:
    return [
        _public(task) for task in sorted(
            _TASKS.values(),
            key=lambda item: item["created_at"],
            reverse=True,
        )[:max(1, min(limit, 100))]
    ]


def control(task_id: str, action: str) -> dict[str, Any]:
    task = _TASKS.get(task_id)
    if not task:
        return {"ok": False, "error": "Tarefa não encontrada."}
    if action == "pause":
        if task["status"] not in {"queued", "running"}:
            return {"ok": False, "error": "Essa tarefa não pode ser pausada agora."}
        task["_resume"].clear()
        task["status"] = "paused"
        _event(task, "paused", "Execução pausada", detail="A pausa ocorre no próximo ponto seguro.")
        return {"ok": True, "task": _public(task)}
    if action == "resume":
        if task["status"] != "paused":
            return {"ok": False, "error": "A tarefa não está pausada."}
        task["status"] = "running"
        task["_resume"].set()
        _event(task, "resumed", "Execução retomada")
        return {"ok": True, "task": _public(task)}
    if action == "cancel":
        if task["status"] in {"completed", "failed", "cancelled", "rejected"}:
            return {"ok": False, "error": "Essa tarefa já terminou."}
        task["_cancel"].set()
        task["_resume"].set()
        runner = task.get("_runner")
        if runner and not runner.done():
            runner.cancel()
        return {"ok": True, "task": _public(task)}
    return {"ok": False, "error": "Controle desconhecido."}


async def apply_task(
    task_id: str,
    paths: list[str] | None,
    confirmed: bool,
) -> dict[str, Any]:
    task = _TASKS.get(task_id)
    if not task or task["status"] != "awaiting_review" or not task.get("plan_id"):
        return {"ok": False, "error": "A tarefa não possui uma proposta pronta."}
    task["status"] = "applying"
    _event(task, "apply", "Aplicando alterações aprovadas", progress=100)
    result = await code_agent.apply(task["plan_id"], confirmed, paths)
    task["result"] = {**(task.get("result") or {}), "apply": result}
    if result.get("ok"):
        task["status"] = "completed"
        _event(task, "success", "Alterações aplicadas", progress=100, detail=", ".join(result.get("applied", [])))
    else:
        task["status"] = "awaiting_review"
        task["error"] = result.get("error")
        _event(task, "error", "Não foi possível aplicar", detail=task["error"] or "")
    _persist()
    return result


def reject_task(task_id: str) -> dict[str, Any]:
    task = _TASKS.get(task_id)
    if not task or task["status"] != "awaiting_review":
        return {"ok": False, "error": "A tarefa não está aguardando revisão."}
    if task.get("plan_id"):
        code_agent.discard(task["plan_id"])
    task["status"] = "rejected"
    _event(task, "rejected", "Proposta rejeitada", detail="Nenhum arquivo foi alterado.")
    return {"ok": True, "task": _public(task)}


_load_archived()
