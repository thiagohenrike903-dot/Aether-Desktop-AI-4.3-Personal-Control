"""FastAPI app — the central HTTP/WS surface for the Aether core.

The Electron main process (or a developer using ``uvicorn`` directly)
imports ``app`` and exposes its routes. Every endpoint here does *real*
work: it does not return mock data.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import importlib.util
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import (
    automations,
    agent_governance,
    audit_integrity,
    browser_agent,
    calendar_client,
    code_agent,
    connections,
    conversations,
    email_client,
    evaluations,
    experience_profiles,
    file_crypto,
    file_organizer,
    git_integration,
    memory,
    model_lab,
    model_profiles,
    operations,
    orchestrator,
    os_control,
    pdf_processor,
    permissions,
    privacy_control,
    plugin_system,
    project_library,
    response_verifier,
    safety_mode,
    skills,
    simulations,
    system_health,
    task_manager,
    tts,
    weather,
    web_search,
    workspace,
    workspace_backup,
    workflows,
    user_backup,
)
from . import llm as llm_module
from .agents import build_default_agents
from .config import settings
from .executor import assess_risk
from .executor import run as run_action
from .executor import undo as undo_action

try:
    from . import vision
except ImportError:
    vision = None  # type: ignore[assignment]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("aether")

APP_VERSION = "4.3.0"
_CANCELLED_REQUESTS: dict[str, float] = {}
_ACTIVE_REQUEST_TASKS: dict[str, asyncio.Task[Any]] = {}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_AUTOMATION_SCHEDULER_TASK: asyncio.Task[Any] | None = None
_PERMISSION_COVERAGE: dict[str, list[str]] = {
    "workspace": [
        "action:workspace_set",
        "action:workspace_write",
        "action:workspace_create",
        "action:workspace_rename",
        "action:workspace_delete",
        "action:workspace_run",
    ],
    "files": [
        "action:file_operation",
        "action:organize_files",
        "action:clean_temp_files",
        "action:undo_organize_files",
    ],
    "git": [
        "action:git_status",
        "action:git_log",
        "action:git_diff",
        "action:git_branch",
        "action:git_commit",
        "action:git_push",
        "action:git_pull",
        "action:git_branch_create",
        "action:git_branch_checkout",
        "action:git_merge",
    ],
    "email": ["action:email_list", "action:email_search", "action:email_send"],
    "calendar": [
        "action:calendar_list",
        "action:calendar_create",
        "action:calendar_delete",
    ],
    "os": [
        "action:kill_app",
        "action:system_action",
        "action:set_volume",
        "action:set_brightness",
        "action:media_command",
        "action:open_app",
        "action:open_path",
        "action:open_url",
    ],
    "backup": [
        "action:backup_create",
        "action:backup_list",
        "action:backup_restore",
    ],
    "crypto": [
        "action:crypto_encrypt",
        "action:crypto_decrypt",
        "action:crypto_encrypt_text",
        "action:crypto_decrypt_text",
    ],
    "plugins": [
        "action:plugin_list",
        "action:plugin_load",
        "action:plugin_unload",
        "action:plugin_reload",
        "action:plugin_install",
        "action:plugin_run",
    ],
    "browser": [
        "action:browser_navigate",
        "action:browser_screenshot",
        "action:browser_click",
        "action:browser_fill",
    ],
}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _AUTOMATION_SCHEDULER_TASK
    _AUTOMATION_SCHEDULER_TASK = asyncio.create_task(
        automations.scheduler_loop(_automation_execute),
        name="aether-automation-scheduler",
    )
    try:
        yield
    finally:
        if _AUTOMATION_SCHEDULER_TASK and not _AUTOMATION_SCHEDULER_TASK.done():
            _AUTOMATION_SCHEDULER_TASK.cancel()
            try:
                await _AUTOMATION_SCHEDULER_TASK
            except asyncio.CancelledError:
                pass
        _AUTOMATION_SCHEDULER_TASK = None
        permissions.reset_session()


app = FastAPI(
    title="Aether Desktop AI Core",
    version=APP_VERSION,
    description=(
        "Local-first desktop intelligence with multi-agent orchestration, "
        "workspace tools, computer vision, voice and semantic memory."
    ),
    lifespan=_lifespan,
)

# CORS is limited to the local development UI. Electron uses authenticated IPC.
_LOCAL_UI_ORIGINS = {
    "http://127.0.0.1:3000",
    "http://localhost:3000",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_LOCAL_UI_ORIGINS),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Aether-Token",
        "X-Aether-Confirmed",
        "X-Aether-Project-Id",
    ],
)

_CONTROL_MUTATION_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (method, re.compile(pattern), action_kind)
    for method, pattern, action_kind in [
        ("PUT", r"^/safety-mode$", "safety_mode_update"),
        ("POST", r"^/projects$", "project_create"),
        ("PATCH", r"^/projects/[^/]+$", "project_update"),
        ("DELETE", r"^/projects/[^/]+$", "project_delete"),
        ("POST", r"^/projects/[^/]+/documents/(?:import|import-folder)$", "document_import"),
        ("DELETE", r"^/projects/[^/]+/documents/[^/]+$", "document_delete"),
        ("POST", r"^/projects/[^/]+/(?:reindex|semantic-index)$", "document_reindex"),
        ("PUT", r"^/projects/[^/]+/safety-policy$", "safety_project_policy_update"),
        ("DELETE", r"^/projects/[^/]+/safety-policy$", "safety_project_policy_update"),
        ("POST", r"^/memories$", "memory_create"),
        ("PATCH", r"^/memories/[^/]+$", "memory_update"),
        ("DELETE", r"^/memories/[^/]+$", "memory_delete"),
        ("POST", r"^/memory/(?:facts|preferences|project)$", "memory_create"),
        ("DELETE", r"^/memory/(?:turns|sessions|facts|preferences|project)/[^/]+$", "memory_delete"),
        ("POST", r"^/skills$", "skill_create"),
        ("PUT", r"^/skills/[^/]+$", "skill_update"),
        ("DELETE", r"^/skills/[^/]+$", "skill_delete"),
        ("POST", r"^/skills/(?:import|[^/]+/duplicate|[^/]+/restore/[^/]+)$", "skill_restore"),
        ("POST", r"^/automations$", "automation_create"),
        ("PATCH", r"^/automations/[^/]+$", "automation_update"),
        ("DELETE", r"^/automations/[^/]+$", "automation_delete"),
        ("POST", r"^/automations/[^/]+/run$", "automation_run"),
        ("POST", r"^/model-profiles$", "model_profile_update"),
        ("PATCH", r"^/model-profiles/[^/]+$", "model_profile_update"),
        ("DELETE", r"^/model-profiles/[^/]+$", "model_profile_update"),
        ("PUT", r"^/model-profiles/active$", "model_profile_activate"),
        ("POST", r"^/model-profiles/[^/]+/(?:clone|reset-usage)$", "model_profile_update"),
        ("POST", r"^/experience-profiles$", "experience_profile_create"),
        ("PATCH", r"^/experience-profiles/[^/]+$", "experience_profile_update"),
        ("DELETE", r"^/experience-profiles/[^/]+$", "experience_profile_delete"),
        ("PUT", r"^/experience-profiles/active$", "experience_profile_activate"),
        ("POST", r"^/connections/test$", "connection_test"),
        ("PUT", r"^/permissions/.+$", "permission_update"),
        ("DELETE", r"^/permissions/.+$", "permission_delete"),
        ("POST", r"^/permissions/session/reset$", "permission_reset"),
        ("POST", r"^/conversations$", "conversation_create"),
        ("PATCH", r"^/conversations/[^/]+$", "conversation_update"),
        ("DELETE", r"^/conversations/[^/]+$", "conversation_delete"),
        ("POST", r"^/conversations/[^/]+/messages$", "message_create"),
        ("PATCH", r"^/conversations/[^/]+/messages/[^/]+$", "message_update"),
        ("DELETE", r"^/conversations/[^/]+/messages/[^/]+$", "message_delete"),
        ("POST", r"^/workflows$", "workflow_create"),
        ("PATCH", r"^/workflows/[^/]+$", "workflow_update"),
        ("DELETE", r"^/workflows/[^/]+$", "workflow_delete"),
        ("POST", r"^/workflows/[^/]+/run$", "workflow_run"),
        ("POST", r"^/workflows/[^/]+/restore/[^/]+$", "workflow_restore"),
        ("POST", r"^/workflows/from-operations$", "workflow_create"),
        ("PUT", r"^/privacy(?:/conversations/[^/]+)?$", "privacy_mode_update"),
        ("DELETE", r"^/privacy/conversations/[^/]+$", "privacy_mode_update"),
        ("POST", r"^/model-lab/presets$", "model_lab_preset_create"),
        ("POST", r"^/model-lab/compare$", "model_lab_compare"),
        ("POST", r"^/model-lab/runs/[^/]+/winner$", "model_lab_select_winner"),
        ("POST", r"^/model-lab/runs/[^/]+/profile$", "model_lab_create_profile"),
        ("POST", r"^/simulations$", "simulation_create"),
        ("POST", r"^/simulations/[^/]+/approve$", "simulation_approve"),
        ("POST", r"^/safety-mode/resume$", "component_resume"),
        ("POST", r"^/system-health/repair$", "system_health_repair"),
        ("POST", r"^/user-backup/create$", "backup_create"),
        ("POST", r"^/user-backup/restore$", "backup_restore"),
        ("POST", r"^/simulations/[^/]+/convert$", "simulation_convert"),
        ("POST", r"^/evaluations/cases$", "evaluation_case_create"),
        ("POST", r"^/evaluations/presets$", "evaluation_preset_create"),
        ("POST", r"^/evaluations/run$", "evaluation_run"),
    ]
)

_CONTROL_BODY_PROJECT_ACTIONS = frozenset({
    "automation_create",
    "automation_update",
    "conversation_create",
    "conversation_update",
    "memory_create",
    "model_lab_compare",
    "simulation_create",
    "system_health_repair",
    "workflow_create",
    "workflow_run",
})
_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,239}$")


def _control_mutation(path: str, method: str) -> tuple[str, str | None] | None:
    for expected_method, pattern, action_kind in _CONTROL_MUTATION_RULES:
        match = pattern.fullmatch(path)
        if expected_method == method and match:
            segments = [segment for segment in path.split("/") if segment]
            project_id = (
                segments[1]
                if len(segments) >= 2 and segments[0] == "projects"
                else None
            )
            return action_kind, project_id
    return None


def _append_control_project_id(
    output: list[str],
    value: Any,
    *,
    source: str,
) -> None:
    if value is None or str(value).strip() == "":
        return
    identifier = str(value).strip()
    if not _PROJECT_ID_PATTERN.fullmatch(identifier):
        raise ValueError(f"Identificador de projeto inválido em {source}.")
    if identifier not in output:
        output.append(identifier)


def _append_workflow_project_ids(
    output: list[str],
    workflow: dict[str, Any] | None,
    *,
    source: str,
) -> None:
    for step in (workflow or {}).get("steps") or []:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if not isinstance(action, dict):
            continue
        value = action.get("project_id")
        # A typed workflow variable is resolved and checked during preview/run;
        # only a literal project id can scope definition edits here.
        if isinstance(value, str) and "${" in value:
            continue
        _append_control_project_id(output, value, source=source)


def _resource_project_ids(path: str) -> list[str]:
    """Resolve project scope from persisted resources, never UI state."""
    segments = [segment for segment in path.split("/") if segment]
    output: list[str] = []
    item: dict[str, Any] | None = None
    if len(segments) >= 2 and segments[0] == "projects":
        _append_control_project_id(output, segments[1], source="rota")
    elif len(segments) >= 2 and segments[0] == "conversations":
        item = conversations.get(segments[1])
        _append_control_project_id(
            output,
            (item or {}).get("project_id"),
            source="conversa",
        )
    elif (
        len(segments) >= 3
        and segments[0] == "privacy"
        and segments[1] == "conversations"
    ):
        item = conversations.get(segments[2])
        _append_control_project_id(
            output,
            (item or {}).get("project_id"),
            source="conversa",
        )
    elif len(segments) >= 2 and segments[0] == "memories":
        item = memory.get_memory(segments[1])
        _append_control_project_id(
            output,
            (item or {}).get("project_id"),
            source="memória",
        )
    elif (
        len(segments) >= 3
        and segments[0] == "memory"
        and segments[1] == "project"
    ):
        item = memory.get_memory(segments[2])
        _append_control_project_id(
            output,
            (item or {}).get("project_id"),
            source="memória",
        )
    elif len(segments) >= 2 and segments[0] == "automations":
        item = automations.get(segments[1])
        action = (item or {}).get("action")
        _append_control_project_id(
            output,
            action.get("project_id") if isinstance(action, dict) else None,
            source="automação",
        )
    elif len(segments) >= 2 and segments[0] == "simulations":
        item = simulations.get(segments[1])
        _append_control_project_id(
            output,
            (item or {}).get("project_id"),
            source="simulação",
        )
    elif (
        len(segments) >= 2
        and segments[0] == "workflows"
        and segments[1] != "from-operations"
    ):
        item = workflows.get_workflow(segments[1])
        _append_workflow_project_ids(
            output,
            item,
            source="workflow",
        )
        if len(segments) >= 4 and segments[2] == "restore":
            revision_id = segments[3]
            for revision in workflows.list_revisions(segments[1]) if item else []:
                if str(revision.get("id")) == revision_id:
                    snapshot = revision.get("snapshot")
                    _append_workflow_project_ids(
                        output,
                        snapshot if isinstance(snapshot, dict) else None,
                        source="revisão de workflow",
                    )
                    break
    elif (
        len(segments) >= 3
        and segments[0] == "model-lab"
        and segments[1] == "runs"
    ):
        item = model_lab.get_run(segments[2])
        context = (item or {}).get("context")
        _append_control_project_id(
            output,
            context.get("project_id") if isinstance(context, dict) else None,
            source="Model Lab",
        )
    return output


async def _body_project_ids(
    request: Request,
    *,
    action_kind: str,
) -> list[str]:
    if action_kind not in _CONTROL_BODY_PROJECT_ACTIONS:
        return []
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type != "application/json":
        return []
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        content_length = 0
    if content_length > 2_000_000:
        raise ValueError("O controle de projeto recusou um corpo excessivamente grande.")
    raw = await request.body()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    output: list[str] = []
    _append_control_project_id(
        output,
        payload.get("project_id"),
        source="corpo da solicitação",
    )
    action = payload.get("action")
    if isinstance(action, dict):
        _append_control_project_id(
            output,
            action.get("project_id"),
            source="ação",
        )
    for raw_step in payload.get("steps") or []:
        if not isinstance(raw_step, dict):
            continue
        step_action = raw_step.get("action")
        if isinstance(step_action, dict):
            _append_control_project_id(
                output,
                step_action.get("project_id"),
                source="etapa",
            )
    if action_kind == "workflow_create":
        for operation_id in payload.get("operation_ids") or []:
            operation = operations.get(str(operation_id))
            operation_action = (operation or {}).get("action")
            if isinstance(operation_action, dict):
                _append_control_project_id(
                    output,
                    operation_action.get("project_id"),
                    source="operação",
                )
    return output


async def _control_project_ids(
    request: Request,
    *,
    action_kind: str,
    path_project_id: str | None,
) -> list[str]:
    output = _resource_project_ids(request.url.path)
    _append_control_project_id(output, path_project_id, source="rota")
    body_ids = await _body_project_ids(request, action_kind=action_kind)
    for identifier in body_ids:
        _append_control_project_id(output, identifier, source="corpo")
    _append_control_project_id(
        output,
        request.headers.get("x-aether-project-id"),
        source="cabeçalho",
    )
    return output


@app.middleware("http")
async def secure_local_api(request: Request, call_next):
    """Require the per-launch Electron token when one is configured.

    Direct local development remains available when ``AETHER_API_TOKEN`` is
    unset. Electron always sets it, preventing unrelated local pages from
    invoking file-system or operating-system actions.
    """
    public_path = request.url.path in {"/", "/health"}
    if (
        settings.api_token
        and not public_path
        and request.method.upper() != "OPTIONS"
    ):
        provided = request.headers.get("x-aether-token", "")
        if not hmac.compare_digest(provided, settings.api_token):
            return JSONResponse(
                status_code=401,
                content={"ok": False, "detail": "Acesso local não autorizado."},
            )

    controlled = _control_mutation(
        request.url.path,
        request.method.upper(),
    )
    if controlled:
        action_kind, path_project_id = controlled
        try:
            project_ids = await _control_project_ids(
                request,
                action_kind=action_kind,
                path_project_id=path_project_id,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "detail": str(exc)},
            )
        confirmed = request.headers.get(
            "x-aether-confirmed", ""
        ).strip().casefold() in {"1", "true", "yes", "sim"}
        # Safety policies must be escapable without weakening the confirmation
        # boundary. A read-only policy would otherwise block the very request
        # needed to change that policy. These two control actions therefore
        # require an explicit confirmation in every mode, then proceed.
        policy_control = action_kind in {
            "safety_mode_update",
            "safety_project_policy_update",
        }
        decision = (
            {
                "blocked": False,
                "requires_confirmation": not confirmed,
                "reason": (
                    "Alterar uma política de proteção exige confirmação explícita."
                ),
                "action_kind": action_kind,
                "project_id": project_ids[0] if len(project_ids) == 1 else None,
                "project_ids": project_ids,
            }
            if policy_control
            else None
        )
        if decision is None:
            decisions = [
                safety_mode.preview(
                    action_kind,
                    confirmed=confirmed,
                    project_id=project_id,
                )
                for project_id in (project_ids or [None])
            ]
            decision = (
                next((item for item in decisions if item["blocked"]), None)
                or next(
                    (item for item in decisions if item["requires_confirmation"]),
                    None,
                )
                or decisions[0]
            )
            decision = {
                **decision,
                "project_ids": project_ids,
            }
        if decision["blocked"]:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "blocked": True,
                    "detail": decision["reason"],
                    "safety": decision,
                },
            )
        if decision["requires_confirmation"]:
            return JSONResponse(
                status_code=428,
                content={
                    "ok": False,
                    "pending_confirmation": True,
                    "detail": decision["reason"],
                    "safety": decision,
                },
            )

    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Aether-Version"] = APP_VERSION
    response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


# Build agents once at startup.
_AGENTS = build_default_agents()

_CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "chat",
        "name": "Conversa inteligente",
        "description": "Respostas contextuais com múltiplos agentes e memória.",
        "category": "intelligence",
        "endpoint": "/chat",
    },
    {
        "id": "vision",
        "name": "Análise visual",
        "description": "Interpreta capturas de tela e imagens anexadas.",
        "category": "intelligence",
        "endpoint": "/vlm/analyze",
        "optional": True,
    },
    {
        "id": "memory",
        "name": "Memória controlável",
        "description": "Fatos, preferências, sessões e memórias por projeto.",
        "category": "intelligence",
        "endpoint": "/memory/overview",
    },
    {
        "id": "control_center",
        "name": "Central de Controle",
        "description": "Operações, aprovações, permissões, repetição e desfazer seguro.",
        "category": "productivity",
        "endpoint": "/operations",
    },
    {
        "id": "context_inspector",
        "name": "Inspetor de contexto",
        "description": "Prévia redigida do contexto e do mapa de privacidade.",
        "category": "security",
        "endpoint": "/context/preview",
    },
    {
        "id": "safety_mode",
        "name": "Modo seguro",
        "description": "Teto global normal, confirmar tudo ou somente leitura.",
        "category": "security",
        "endpoint": "/safety-mode",
    },
    {
        "id": "audit_export",
        "name": "Exportação de auditoria",
        "description": "Operações e eventos redigidos em JSON com checksum.",
        "category": "security",
        "endpoint": "/audit/export",
    },
    {
        "id": "personal_home",
        "name": "Painel personalizável",
        "description": "Organizações independentes para trabalho, estudo e uso pessoal.",
        "category": "productivity",
        "endpoint": "/experience-profiles",
    },
    {
        "id": "model_lab",
        "name": "Model Lab",
        "description": "Compara duas respostas com o mesmo contexto e métricas locais.",
        "category": "intelligence",
        "endpoint": "/model-lab/compare",
    },
    {
        "id": "response_verifier",
        "name": "Verificador de resposta",
        "description": "Classifica afirmações como sustentadas, inferências ou sem evidência.",
        "category": "research",
        "endpoint": "/responses/verify",
    },
    {
        "id": "workflows",
        "name": "Workflows reutilizáveis",
        "description": "Templates versionados com variáveis, prévia e restauração.",
        "category": "productivity",
        "endpoint": "/workflows",
    },
    {
        "id": "system_health",
        "name": "Saúde do sistema",
        "description": "Diagnósticos persistentes e reparos reversíveis.",
        "category": "security",
        "endpoint": "/system-health/check",
    },
    {
        "id": "personal_evaluations",
        "name": "Avaliações pessoais",
        "description": "Casos reais e bloqueio de atualizações que regredirem critérios essenciais.",
        "category": "intelligence",
        "endpoint": "/evaluations/cases",
    },
    {
        "id": "projects",
        "name": "Projetos e biblioteca",
        "description": "Conversas, memórias e documentos com citações por projeto.",
        "category": "documents",
        "endpoint": "/projects",
    },
    {
        "id": "automations",
        "name": "Automações visuais",
        "description": "Gatilhos locais com simulação, aprovação e histórico.",
        "category": "productivity",
        "endpoint": "/automations",
    },
    {
        "id": "model_profiles",
        "name": "Perfis de modelo",
        "description": "Seleção, fallback, limites e uso local estimado.",
        "category": "intelligence",
        "endpoint": "/model-profiles",
    },
    {
        "id": "web_search",
        "name": "Pesquisa na web",
        "description": "Abre fontes públicas com conexão DNS/IP pinada.",
        "category": "research",
        "endpoint": "/web/search",
    },
    {
        "id": "browser_automation",
        "name": "Automação de navegador",
        "description": (
            "Desativada até existir um proxy de saída auditável com DNS/IP pinado."
        ),
        "category": "research",
        "endpoint": "/browser/status",
        "optional": True,
        "enabled": browser_agent.NETWORK_AUTOMATION_ENABLED,
        "status": "disabled_security",
    },
    {
        "id": "workspace",
        "name": "Workspace de código",
        "description": "Explora, pesquisa, cria e edita projetos com proteção de conflitos.",
        "category": "creation",
        "endpoint": "/workspace",
    },
    {
        "id": "code_agent",
        "name": "Agente de código",
        "description": "Planeja alterações, cria checkpoints e permite desfazer.",
        "category": "creation",
        "endpoint": "/code/plan",
    },
    {
        "id": "skills",
        "name": "Skills personalizadas",
        "description": "Cria instruções especializadas, testa e restaura revisões.",
        "category": "creation",
        "endpoint": "/skills",
    },
    {
        "id": "tasks",
        "name": "Central de tarefas",
        "description": "Acompanha tarefas de código, validação e aprovação.",
        "category": "productivity",
        "endpoint": "/tasks",
    },
    {
        "id": "system",
        "name": "Painel do sistema",
        "description": "CPU, memória, processos e controles de mídia.",
        "category": "desktop",
        "endpoint": "/system",
    },
    {
        "id": "file_organizer",
        "name": "Organizador seguro",
        "description": "Pré-visualiza e organiza pastas com opção de desfazer.",
        "category": "desktop",
        "endpoint": "/files/organize",
    },
    {
        "id": "git",
        "name": "Git integrado",
        "description": "Status, histórico, diff, branches e operações remotas.",
        "category": "development",
        "endpoint": "/git/status",
    },
    {
        "id": "pdf",
        "name": "Leitor de PDF",
        "description": "Extrai texto e tabelas de documentos locais.",
        "category": "documents",
        "endpoint": "/pdf/text",
    },
    {
        "id": "document_extract",
        "name": "Leitor de documentos",
        "description": "Extrai conteúdo limitado de PDF, DOCX, XLSX e texto sem persistir.",
        "category": "documents",
        "endpoint": "/documents/extract",
    },
    {
        "id": "crypto",
        "name": "Cofre local",
        "description": "Criptografa textos e arquivos no dispositivo.",
        "category": "security",
        "endpoint": "/crypto/encrypt",
    },
    {
        "id": "backup",
        "name": "Backups de workspace",
        "description": "Cria, lista e restaura cópias de segurança.",
        "category": "security",
        "endpoint": "/backup/create",
    },
    {
        "id": "voice",
        "name": "Voz",
        "description": "Síntese neural ou voz local do navegador.",
        "category": "accessibility",
        "endpoint": "/tts",
        "optional": True,
    },
]


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Aether Desktop AI",
        "version": APP_VERSION,
        "voice_id": settings.elevenlabs_voice_id,
        "agents": [a.id for a in _AGENTS],
        "providers": {
            "llm": settings.llm_provider,
            "model": settings.llm_model or settings.agent_orchestrator_model,
            "tts": "elevenlabs" if settings.elevenlabs_api_key else "browser",
        },
        "endpoints": [
            "/health", "/diagnostics", "/capabilities", "/chat", "/chat/stream",
            "/command", "/tts", "/voices", "/memory/overview",
            "/memories", "/operations", "/permissions", "/conversations",
            "/projects", "/documents/extract", "/research", "/context/preview",
            "/safety-mode", "/audit/export",
            "/model-profiles", "/automations",
            "/vision/analyze", "/system", "/os/apps", "/os/processes",
            "/os/file", "/os/volume", "/os/brightness", "/os/media",
            "/workspace", "/code/plan", "/code/apply",
            "/web/search", "/web/fetch", "/git/*", "/email/*",
            "/weather/*", "/pdf/*", "/crypto/*", "/backup/*",
            "/plugins/*", "/browser/*", "/vlm/analyze", "/llm/provider",
        ],
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "aether-core", "version": APP_VERSION, "ts": time.time()}


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Machine-readable catalogue used by the tools panel."""
    return {
        "ok": True,
        "version": APP_VERSION,
        "capabilities": _CAPABILITIES,
        "categories": [
            "intelligence",
            "research",
            "creation",
            "productivity",
            "desktop",
            "development",
            "documents",
            "security",
            "accessibility",
        ],
    }


@app.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    """Return redacted readiness information without exposing credentials."""
    workspace_root = workspace.get_root()
    vision_features = {
        "frames": vision is not None,
        "faces": importlib.util.find_spec("face_recognition") is not None,
        "hands_pose": importlib.util.find_spec("mediapipe") is not None,
        "ocr": (
            importlib.util.find_spec("pytesseract") is not None
            and shutil.which("tesseract") is not None
        ),
        "barcodes": importlib.util.find_spec("pyzbar") is not None,
    }
    checks = [
        {
            "id": "core",
            "name": "Núcleo local",
            "ok": True,
            "required": True,
        },
        {
            "id": "storage",
            "name": "Armazenamento local",
            "ok": settings.data_dir.exists() and os.access(settings.data_dir, os.W_OK),
            "required": True,
        },
        {
            "id": "llm",
            "name": "Modelo de linguagem",
            "ok": llm_module.is_configured(),
            "required": False,
            "detail": (
                f"{settings.llm_provider} · "
                f"{settings.llm_model or settings.agent_orchestrator_model}"
            ),
        },
        {
            "id": "vision",
            "name": "Visão computacional",
            "ok": vision is not None,
            "required": False,
            "detail": ", ".join(
                name for name, available in vision_features.items() if available
            ) or "Pacote opcional não instalado",
            "features": vision_features,
        },
        {
            "id": "semantic_memory",
            "name": "Memória semântica",
            "ok": (
                importlib.util.find_spec("chromadb") is not None
                and importlib.util.find_spec("sentence_transformers") is not None
            ),
            "required": False,
        },
        {
            "id": "workspace",
            "name": "Workspace",
            "ok": workspace_root is not None,
            "required": False,
            "detail": workspace_root.name if workspace_root else "Nenhum projeto selecionado",
        },
        {
            "id": "browser_automation",
            "name": "Automação de navegador",
            "ok": browser_agent.NETWORK_AUTOMATION_ENABLED,
            "required": False,
            "detail": browser_agent.status()["detail"],
        },
    ]
    required_ready = all(item["ok"] for item in checks if item["required"])
    return {
        "ok": required_ready,
        "status": "ready" if required_ready else "degraded",
        "checks": checks,
        "runtime": {
            "platform": platform.system(),
            "platform_version": platform.release(),
            "python": platform.python_version(),
        },
    }


@app.get("/system")
async def system_snapshot() -> dict[str, Any]:
    """Live CPU / memory / process snapshot for the HUD telemetry."""
    snap = await os_control.system_snapshot()
    snap["voice_id"] = settings.elevenlabs_voice_id
    snap["agents"] = [a.id for a in _AGENTS]
    return snap


# --------------------------------------------------------------------------- #
# Chat / command
# --------------------------------------------------------------------------- #

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        min_length=1,
        max_length=160,
    )
    intent_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, min_length=8, max_length=128)
    execute: bool = True  # whether to actually run the structured action
    confirm_actions: bool = False
    conversation_id: str | None = Field(default=None, min_length=1, max_length=160)
    parent_message_id: str | None = Field(default=None, min_length=1, max_length=160)
    branch_id: str | None = Field(default=None, min_length=1, max_length=160)
    project_id: str | None = Field(default=None, min_length=1, max_length=160)
    model_profile_id: str | None = Field(default=None, min_length=1, max_length=120)


class ContextPreviewRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    session_id: str = Field(default="context-preview", min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=160)
    parent_message_id: str | None = Field(default=None, min_length=1, max_length=160)
    branch_id: str | None = Field(default=None, min_length=1, max_length=160)
    project_id: str | None = Field(default=None, min_length=1, max_length=160)
    model_profile_id: str | None = Field(default=None, min_length=1, max_length=120)
    action: dict[str, Any] | None = None


class CommandRequest(BaseModel):
    command: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class FileRequest(BaseModel):
    action: str
    src: str
    dst: str | None = None
    confirm: bool = False


def _chat_metadata(req: ChatRequest) -> dict[str, Any]:
    metadata = dict(req.metadata)
    for reserved in (
        "project_id",
        "model_profile_id",
        "conversation_id",
        "parent_message_id",
        "branch_id",
    ):
        metadata.pop(reserved, None)
    if req.project_id:
        metadata["project_id"] = req.project_id
    if req.model_profile_id:
        metadata["model_profile_id"] = req.model_profile_id
    if req.conversation_id:
        metadata["conversation_id"] = req.conversation_id
    if req.parent_message_id:
        metadata["parent_message_id"] = req.parent_message_id
    if req.branch_id:
        metadata["branch_id"] = req.branch_id
    return metadata


def _resolve_conversation_binding(
    *,
    conversation_id: str | None,
    project_id: str | None,
    parent_message_id: str | None,
    attach_project: bool,
) -> str | None:
    if not conversation_id:
        if parent_message_id:
            raise HTTPException(
                status_code=400,
                detail="Uma mensagem pai exige uma conversa existente.",
            )
        return project_id
    conversation = conversations.get(conversation_id)
    if conversation is None:
        if parent_message_id:
            raise HTTPException(
                status_code=400,
                detail="A mensagem pai não existe na nova conversa.",
            )
        return project_id
    stored_project_id = conversation.get("project_id")
    if (
        stored_project_id
        and project_id
        and str(stored_project_id) != str(project_id)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "A conversa pertence a outro projeto. "
                "Altere o projeto da conversa explicitamente antes de continuar."
            ),
        )
    if parent_message_id and conversations.get_message(
        conversation_id,
        parent_message_id,
    ) is None:
        raise HTTPException(status_code=400, detail="Mensagem pai não encontrada.")
    resolved = str(project_id or stored_project_id or "").strip() or None
    if attach_project and project_id and not stored_project_id:
        conversations.update(conversation_id, {"project_id": project_id})
    return resolved


def _resolve_chat_context(req: ChatRequest) -> None:
    req.project_id = _resolve_conversation_binding(
        conversation_id=req.conversation_id,
        project_id=req.project_id,
        parent_message_id=req.parent_message_id,
        attach_project=True,
    )


def _operational_timeline(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build an auditable activity summary without exposing private reasoning."""
    timeline: list[dict[str, Any]] = [
        {
            "type": "analyzed",
            "label": "Analisado",
            "detail": "Solicitação roteada para os recursos disponíveis.",
        }
    ]
    manifest = result.get("context_manifest")
    if isinstance(manifest, dict):
        counts = {
            "mensagens": len(manifest.get("messages") or []),
            "memórias": len(manifest.get("memories") or []),
            "skills": len(manifest.get("skills") or []),
            "documentos": len(manifest.get("documents") or []),
            "anexos": len(manifest.get("attachments") or []),
        }
        if any(counts.values()):
            timeline.append({
                "type": "read",
                "label": "Lido",
                "detail": (
                    "Contexto autorizado consultado: "
                    + ", ".join(
                        f"{key} {value}"
                        for key, value in counts.items()
                        if value
                    )[:300]
                ),
            })
    citations = result.get("citations")
    if isinstance(citations, list) and citations:
        timeline.append({
            "type": "read",
            "label": "Fontes lidas",
            "detail": f"{len(citations)} fonte(s) utilizada(s) na resposta.",
        })
    action = result.get("action")
    if isinstance(action, dict):
        timeline.append({
            "type": "planned",
            "label": "Planejado",
            "detail": (
                f"Ação {str(action.get('type') or 'estruturada')[:100]} "
                "preparada para a política de segurança."
            ),
        })
    operation = result.get("operation")
    if isinstance(operation, dict):
        state = str(operation.get("state") or "")
        if state == "awaiting_approval":
            timeline.append({
                "type": "approval",
                "label": "Aguardando aprovação",
                "detail": "A alteração não foi executada.",
            })
        elif state == "completed":
            timeline.append({
                "type": "changed",
                "label": "Alterado",
                "detail": "A operação aprovada foi concluída.",
            })
        elif state in {"failed", "cancelled"}:
            timeline.append({
                "type": state,
                "label": "Falhou" if state == "failed" else "Cancelado",
                "detail": "Nenhuma conclusão foi ocultada do histórico.",
            })
    return timeline[:20]


def _conversation_exchange(req: ChatRequest, result: dict[str, Any]) -> None:
    if not req.conversation_id:
        return
    conversation = conversations.get(req.conversation_id)
    if conversation is None:
        conversations.create(
            title="Nova conversa",
            project_id=req.project_id,
            conversation_id=req.conversation_id,
        )
    user_message = conversations.add_message(
        req.conversation_id,
        role="user",
        content=req.message,
        parent_id=req.parent_message_id,
        branch_id=req.branch_id,
        metadata={
            "session_id": req.session_id,
            "request_id": req.request_id,
        },
    )
    assistant_message = conversations.add_message(
        req.conversation_id,
        role="assistant",
        content=str(result.get("reply") or ""),
        parent_id=user_message["id"],
        branch_id=user_message["branch_id"],
        metadata={
            "winner": result.get("winner"),
            "citations": result.get("citations") or [],
            "sources": result.get("sources") or result.get("citations") or [],
            "used_memories": result.get("used_memories") or [],
            "context_manifest": result.get("context_manifest") or {},
            "model": result.get("model") or {},
            "metrics": result.get("metrics"),
            "timeline": result.get("timeline") or _operational_timeline(result),
        },
    )
    result["user_message"] = user_message
    result["assistant_message"] = assistant_message


async def _execute_controlled(
    action: dict[str, Any],
    confirmed: bool = False,
    request_id: str | None = None,
    *,
    permission_scope: str | None = None,
    force_approval: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    kind = str(action.get("type") or "").strip().lower()
    if not kind:
        raise ValueError("A ação precisa informar um tipo.")
    derived_scope = permissions.normalize_scope(f"action:{kind}")
    if permission_scope is not None:
        supplied_scope = permissions.normalize_scope(permission_scope)
        if supplied_scope != derived_scope:
            raise ValueError(
                "permission_scope não corresponde ao tipo da ação."
            )
    risk = assess_risk(action)
    operation = operations.create(
        action,
        request_id=request_id,
        permission_scope=derived_scope,
        risk=risk,
    )
    decision = permissions.decision(
        operation["permission_scope"],
        risk=risk,
        confirmed=confirmed,
        project_id=project_id,
    )
    if force_approval and not confirmed and decision == "allow":
        decision = "ask"
    if decision == "block":
        return operations.transition(
            operation["id"],
            "failed",
            error="A operação foi bloqueada pela política de permissões.",
        )
    if decision == "ask":
        return operations.mark_awaiting_approval(operation["id"])
    return await operations.run_existing(
        operation["id"],
        run_action,
        confirmed=True,
    )


async def _execute_direct_action(
    action: dict[str, Any],
    *,
    confirmed: bool = False,
) -> Any:
    """Apply the same policy/operation pipeline to legacy direct routes.

    Direct endpoints keep returning their historical raw tool result on
    success.  The persisted Control Centre copy is independently redacted.
    """
    kind = str(action.get("type") or "").strip().lower()
    if not kind:
        raise HTTPException(status_code=400, detail="A ação precisa informar um tipo.")
    scope = permissions.normalize_scope(f"action:{kind}")
    risk = assess_risk(action)
    operation = operations.create(
        action,
        permission_scope=scope,
        risk=risk,
    )
    decision = permissions.decision(scope, risk=risk, confirmed=confirmed)
    if decision == "block":
        operation = operations.transition(
            operation["id"],
            "failed",
            error="A operação foi bloqueada pela política de permissões.",
        )
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "blocked": True,
                "error": operation["error"],
                "operation": operation,
                "operation_id": operation["id"],
            },
        )
    if decision == "ask":
        operation = operations.mark_awaiting_approval(operation["id"])
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "pending_confirmation": True,
                "risk": operation["risk"],
                "error": "Esta ação precisa de confirmação.",
                "operation": operation,
                "operation_id": operation["id"],
            },
        )
    operation, raw_result = await operations.run_existing_with_result(
        operation["id"],
        run_action,
        confirmed=True,
    )
    if raw_result is None:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": operation.get("error") or "A operação falhou.",
                "operation": operation,
                "operation_id": operation["id"],
            },
        )
    result = dict(raw_result)
    result["operation"] = operation
    result["operation_id"] = operation["id"]
    return result


def _attach_operation(result: dict[str, Any], operation: dict[str, Any]) -> None:
    result["operation"] = operation
    if operation["state"] == "awaiting_approval":
        result["executed"] = {
            "ok": False,
            "pending_confirmation": True,
            "risk": operation["risk"],
            "operation_id": operation["id"],
            "action": operation["action"],
            "error": "Esta ação precisa de confirmação.",
        }
    elif operation["result"] is not None:
        result["executed"] = operation["result"]
    else:
        result["executed"] = {
            "ok": operation["state"] == "completed",
            "operation_id": operation["id"],
            "state": operation["state"],
            "error": operation["error"],
        }


async def _run_chat(req: ChatRequest) -> dict[str, Any]:
    _resolve_chat_context(req)
    request_id = req.request_id
    if request_id and not _REQUEST_ID_PATTERN.fullmatch(request_id):
        raise HTTPException(status_code=400, detail="Identificador de requisição inválido.")
    try:
        if request_id and request_id in _CANCELLED_REQUESTS:
            return {
                "reply": "",
                "action": None,
                "agents": [],
                "winner": "cancelled",
                "used_skills": [],
                "cancelled": True,
                "executed": {"ok": False, "cancelled": True},
            }

        if request_id:
            current_task = asyncio.current_task()
            if current_task:
                _ACTIVE_REQUEST_TASKS[request_id] = current_task
        result = await orchestrator.dispatch(
            req.message,
            session_id=req.session_id,
            intent_hint=req.intent_hint,
            metadata=_chat_metadata(req),
        )
        if request_id and request_id in _CANCELLED_REQUESTS:
            result["cancelled"] = True
            result["executed"] = {"ok": False, "cancelled": True}
            return result
        if req.execute and result.get("action"):
            operation = await _execute_controlled(
                result["action"],
                confirmed=req.confirm_actions,
                request_id=request_id,
                project_id=req.project_id,
            )
            _attach_operation(result, operation)
        if request_id and request_id in _CANCELLED_REQUESTS:
            result["cancelled"] = True
            result.setdefault("executed", {"ok": False, "cancelled": True})
            return result
        result["timeline"] = _operational_timeline(result)
        _conversation_exchange(req, result)
        return result
    finally:
        if request_id:
            _ACTIVE_REQUEST_TASKS.pop(request_id, None)


@app.post("/requests/{request_id}/cancel")
async def cancel_request(request_id: str) -> dict[str, Any]:
    """Cancel native model HTTP streaming and cooperative tools immediately."""
    if not _REQUEST_ID_PATTERN.fullmatch(request_id):
        raise HTTPException(status_code=400, detail="Identificador de requisição inválido.")
    now = time.monotonic()
    stale_before = now - 600
    for stale_id, marked_at in list(_CANCELLED_REQUESTS.items()):
        if marked_at < stale_before:
            _CANCELLED_REQUESTS.pop(stale_id, None)
    _CANCELLED_REQUESTS[request_id] = now
    operation_ids = await operations.cancel_for_request(request_id)
    active_task = _ACTIVE_REQUEST_TASKS.get(request_id)
    if active_task and not active_task.done():
        active_task.cancel()
    return {
        "ok": True,
        "request_id": request_id,
        "cancelled": True,
        "operation_ids": operation_ids,
    }


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Run the multi-agent orchestrator and (optionally) execute the action."""
    return await _run_chat(req)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream native provider deltas as Server-Sent Events."""
    _resolve_chat_context(req)
    request_id = req.request_id or str(uuid.uuid4())
    if not _REQUEST_ID_PATTERN.fullmatch(request_id):
        raise HTTPException(status_code=400, detail="Identificador de requisição inválido.")
    # Persist the actual generated identifier in conversation message metadata,
    # not the optional value originally supplied by the client.
    req.request_id = request_id

    def encode(event: dict[str, Any], sequence: int) -> str:
        item = {
            **event,
            "request_id": request_id,
            "sequence": sequence,
            "ts": time.time(),
        }
        event_type = str(item.get("type") or "message")
        return (
            f"event: {event_type}\n"
            f"id: {request_id}:{sequence}\n"
            f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"
        )

    async def gen():
        sequence = 0
        current_task = asyncio.current_task()
        if current_task:
            _ACTIVE_REQUEST_TASKS[request_id] = current_task
        sequence += 1
        yield encode({
            "type": "accepted",
            "stream_protocol": "sse",
        }, sequence)
        try:
            async for event in orchestrator.dispatch_stream(
                req.message,
                session_id=req.session_id,
                intent_hint=req.intent_hint,
                metadata=_chat_metadata(req),
            ):
                if request_id in _CANCELLED_REQUESTS:
                    raise asyncio.CancelledError
                if event.get("type") == "result":
                    result = event["payload"]
                    if req.execute and result.get("action"):
                        sequence += 1
                        yield encode({
                            "type": "status",
                            "stage": "executing",
                            "message": "Processando a ação estruturada.",
                        }, sequence)
                        operation = await _execute_controlled(
                            result["action"],
                            confirmed=req.confirm_actions,
                            request_id=request_id,
                            project_id=req.project_id,
                        )
                        _attach_operation(result, operation)
                        sequence += 1
                        yield encode({
                            "type": "operation",
                            "operation": operation,
                        }, sequence)
                        if request_id in _CANCELLED_REQUESTS:
                            raise asyncio.CancelledError
                    result["timeline"] = _operational_timeline(result)
                    _conversation_exchange(req, result)
                    sequence += 1
                    yield encode({
                        "type": "done",
                        "payload": result,
                        "stream_mode": event.get("stream_mode"),
                        "usage": event.get("usage"),
                        "fallback_used": event.get("fallback_used", False),
                    }, sequence)
                else:
                    sequence += 1
                    yield encode(event, sequence)
        except asyncio.CancelledError:
            if request_id not in _CANCELLED_REQUESTS:
                raise
            task = asyncio.current_task()
            if task and hasattr(task, "uncancel"):
                while task.cancelling():
                    task.uncancel()
            sequence += 1
            yield encode({
                "type": "cancelled",
                "message": (
                    "Geração cancelada. Ferramentas sem cancelamento cooperativo "
                    "continuam visíveis na Central de Controle."
                ),
            }, sequence)
        except Exception:
            log.exception("Chat stream failed")
            sequence += 1
            yield encode({
                "type": "error",
                "message": "Não foi possível concluir esta resposta.",
            }, sequence)
        finally:
            _ACTIVE_REQUEST_TASKS.pop(request_id, None)
            _CANCELLED_REQUESTS.pop(request_id, None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/context/preview")
async def context_preview(req: ContextPreviewRequest) -> dict[str, Any]:
    """Inspect the exact local context selection without invoking a model."""
    resolved_project_id = _resolve_conversation_binding(
        conversation_id=req.conversation_id,
        project_id=req.project_id,
        parent_message_id=req.parent_message_id,
        attach_project=False,
    )
    metadata = dict(req.metadata)
    for reserved in (
        "project_id",
        "model_profile_id",
        "conversation_id",
        "parent_message_id",
        "branch_id",
    ):
        metadata.pop(reserved, None)
    if resolved_project_id:
        metadata["project_id"] = resolved_project_id
    if req.model_profile_id:
        metadata["model_profile_id"] = req.model_profile_id
    if req.conversation_id:
        metadata["conversation_id"] = req.conversation_id
    if req.parent_message_id:
        metadata["parent_message_id"] = req.parent_message_id
    if req.branch_id:
        metadata["branch_id"] = req.branch_id
    try:
        manifest = await orchestrator.preview_context(
            req.message,
            session_id=req.session_id,
            metadata=metadata,
            action=req.action,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversa ou projeto não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "side_effects": False,
        "context": manifest,
    }


class ActionExecuteRequest(BaseModel):
    action: dict[str, Any]
    confirmed: bool = False
    request_id: str | None = Field(default=None, min_length=8, max_length=128)


@app.post("/actions/execute")
async def action_execute(req: ActionExecuteRequest) -> dict[str, Any]:
    try:
        operation = await _execute_controlled(
            req.action,
            confirmed=req.confirmed,
            request_id=req.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if operation["result"] is not None:
        return {
            **operation["result"],
            "operation": operation,
            "operation_id": operation["id"],
        }
    return {
        "ok": operation["state"] == "completed",
        "pending_confirmation": operation["state"] == "awaiting_approval",
        "blocked": (
            operation["state"] == "failed"
            and "bloqueada" in str(operation.get("error") or "").lower()
        ),
        "risk": operation["risk"],
        "error": operation["error"],
        "operation": operation,
        "operation_id": operation["id"],
    }


class OperationExecuteRequest(BaseModel):
    action: dict[str, Any]
    confirmed: bool = False
    permission_scope: str | None = None
    request_id: str | None = Field(default=None, min_length=8, max_length=128)


@app.get("/operations")
def operation_list(
    state: str | None = None,
    limit: int = 100,
    request_id: str | None = None,
) -> dict[str, Any]:
    try:
        items = operations.list_operations(
            state=state,
            limit=limit,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "operations": items}


@app.get("/operations/{operation_id}")
def operation_get(operation_id: str) -> dict[str, Any]:
    item = operations.get(operation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    return {"ok": True, "operation": item}


@app.get("/operations/{operation_id}/events")
def operation_events(operation_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "events": operations.events(operation_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")


@app.get("/audit/export")
def audit_export(
    limit: int = 500,
    since: float | None = None,
    until: float | None = None,
) -> JSONResponse:
    try:
        payload = operations.export_audit(
            limit=limit,
            since=since,
            until=until,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payload["metadata"]["app_version"] = APP_VERSION
    payload["metadata"]["safety_mode"] = safety_mode.get_mode()
    payload["metadata"]["permission_policy_count"] = len(
        permissions.list_policies()
    )
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": 'attachment; filename="aether-audit.json"',
        },
    )


@app.post("/operations/execute")
async def operation_execute(req: OperationExecuteRequest) -> dict[str, Any]:
    if req.request_id and not _REQUEST_ID_PATTERN.fullmatch(req.request_id):
        raise HTTPException(status_code=400, detail="Identificador de requisição inválido.")
    try:
        operation = await _execute_controlled(
            req.action,
            confirmed=req.confirmed,
            request_id=req.request_id,
            permission_scope=req.permission_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": operation["state"] != "failed", "operation": operation}


@app.post("/operations/{operation_id}/approve")
async def operation_approve(operation_id: str) -> dict[str, Any]:
    existing = operations.get(operation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    policy = permissions.decision(
        existing["permission_scope"],
        risk=existing["risk"],
        confirmed=True,
        project_id=str(existing.get("action", {}).get("project_id") or "") or None,
    )
    if policy == "block":
        try:
            blocked = operations.transition(
                operation_id,
                "failed",
                error="A operação foi bloqueada pela política de permissões atual.",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse(
            status_code=403,
            content={
                "ok": False,
                "blocked": True,
                "operation": blocked,
                "detail": "A política atual bloqueia esta operação.",
            },
        )
    try:
        operation = await operations.run_existing(
            operation_id,
            run_action,
            confirmed=True,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": operation["state"] == "completed", "operation": operation}


@app.post("/operations/{operation_id}/cancel")
async def operation_cancel(operation_id: str) -> dict[str, Any]:
    try:
        operation = await operations.cancel(operation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": operation["state"] == "cancelled", "operation": operation}


@app.post("/operations/{operation_id}/retry")
async def operation_retry(operation_id: str) -> dict[str, Any]:
    try:
        operation = await operations.retry(operation_id, run_action)
    except KeyError:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": operation["state"] != "failed", "operation": operation}


@app.post("/operations/{operation_id}/undo")
async def operation_undo(
    operation_id: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    try:
        return await operations.undo(
            operation_id,
            undo_action,
            confirmed=confirmed,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Operação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


class PermissionRequest(BaseModel):
    mode: str


class SafetyModeRequest(BaseModel):
    mode: str


class SafetyPreviewRequest(BaseModel):
    action: dict[str, Any]
    confirmed: bool = False


class SafetySuspensionRequest(BaseModel):
    reason: str = ""


def _safety_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "safety": safety_mode.get_state(),
        "available_modes": [
            {
                "id": "normal",
                "name": "Normal",
                "description": "Usa as políticas específicas de cada ação.",
            },
            {
                "id": "confirm_all",
                "name": "Confirmar tudo",
                "description": "Toda ação conhecida exige aprovação explícita.",
            },
            {
                "id": "read_only",
                "name": "Somente leitura",
                "description": (
                    "Permite apenas ações de leitura classificadas explicitamente."
                ),
            },
        ],
        "classification": {
            "known_actions": len(safety_mode.KNOWN_ACTIONS),
            "read_actions": len(safety_mode.READ_ONLY_ACTIONS),
            "mutating_actions": len(safety_mode.MUTATING_ACTIONS),
            "unknown_actions_fail_closed_in_restrictive_modes": True,
        },
        "project_policies": safety_mode.list_project_policies(),
        "suspensions": safety_mode.list_suspensions(),
        "emergency_stop": {
            "components": sorted(safety_mode.SUSPENDABLE_COMPONENTS),
            "terminates_in_flight_plugin_threads": False,
        },
        "simulation_supported": False,
        "simulation_note": (
            "O modo seguro avalia e bloqueia ações; ele não simula efeitos "
            "de ferramentas que não oferecem dry-run real."
        ),
    }


@app.get("/safety-mode")
def safety_mode_get() -> dict[str, Any]:
    return _safety_payload()


@app.put("/safety-mode")
def safety_mode_set(req: SafetyModeRequest) -> dict[str, Any]:
    try:
        safety_mode.set_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _safety_payload()


@app.post("/safety-mode/preview")
def safety_mode_preview(req: SafetyPreviewRequest) -> dict[str, Any]:
    preview = safety_mode.preview(req.action, confirmed=req.confirmed)
    return {
        "ok": True,
        "side_effects": False,
        "simulation_supported": False,
        "preview": {
            **preview,
            "risk": assess_risk(req.action),
            "affected": operations.affected_resources(req.action),
        },
    }


@app.post("/safety-mode/emergency-suspend")
async def safety_emergency_suspend(
    req: SafetySuspensionRequest,
) -> dict[str, Any]:
    result = await plugin_system.suspend_all(req.reason)
    return {
        **result,
        "safety": _safety_payload(),
    }


@app.post("/safety-mode/resume")
def safety_resume() -> dict[str, Any]:
    return {
        **plugin_system.resume_all(),
        "safety": _safety_payload(),
    }


@app.get("/projects/{project_id}/safety-policy")
def project_safety_policy_get(project_id: str) -> dict[str, Any]:
    return {
        "ok": True,
        "project_id": project_id,
        "policy": safety_mode.get_project_policy(project_id),
        "effective": safety_mode.effective_mode(project_id=project_id),
    }


@app.put("/projects/{project_id}/safety-policy")
def project_safety_policy_set(
    project_id: str,
    req: SafetyModeRequest,
) -> dict[str, Any]:
    if project_library.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    try:
        policy = safety_mode.set_project_policy(project_id, req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "policy": policy,
        "effective": safety_mode.effective_mode(project_id=project_id),
    }


@app.delete("/projects/{project_id}/safety-policy")
def project_safety_policy_delete(project_id: str) -> dict[str, Any]:
    return {
        "ok": safety_mode.delete_project_policy(project_id),
        "project_id": project_id,
    }


@app.get("/permissions")
def permission_list() -> dict[str, Any]:
    return {
        "ok": True,
        "policies": permissions.list_policies(),
        "available_modes": ["ask", "session_allow", "block"],
    }


@app.get("/permissions/capabilities")
def permission_capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "modes": ["ask", "session_allow", "block"],
        "scope_format": "action:<tipo>",
        "precedence": ["exact", "category_wildcard", "global_wildcard"],
        "block_overrides_confirmation": True,
        "session_allow_persisted": False,
        "direct_route_coverage": _PERMISSION_COVERAGE,
        "disabled_categories": {
            "browser": browser_agent.status()["detail"],
        },
        "global_safety": _safety_payload(),
    }


@app.put("/permissions/{scope:path}")
def permission_set(scope: str, req: PermissionRequest) -> dict[str, Any]:
    try:
        policy = permissions.set_policy(scope, req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "policy": policy}


@app.delete("/permissions/{scope:path}")
def permission_delete(scope: str) -> dict[str, Any]:
    try:
        deleted = permissions.delete_policy(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": deleted}


@app.post("/permissions/session/reset")
def permission_reset_session() -> dict[str, Any]:
    return {"ok": True, "deleted": permissions.reset_session()}


# --------------------------------------------------------------------------- #
# Model profiles
# --------------------------------------------------------------------------- #

class ActiveProfileRequest(BaseModel):
    profile_id: str


class ModelProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    cost_limit_usd: float | None = None
    cost_input_per_million: float | None = None
    cost_output_per_million: float | None = None
    fallback_profile_id: str | None = None
    vision: bool | None = None
    offline: bool | None = None
    enabled: bool | None = None


@app.get("/model-profiles")
def model_profile_list() -> dict[str, Any]:
    active_id = model_profiles.get_active_profile_id()
    profiles = []
    for profile in model_profiles.list_profiles():
        usage = model_profiles.get_usage(profile["id"])
        usage = {
            **usage,
            "cost_usd": usage["estimated_cost_usd"],
            "cost": usage["estimated_cost_usd"],
        }
        profiles.append({
            **profile,
            "active": profile["id"] == active_id,
            "usage": usage,
        })
    return {
        "ok": True,
        "profiles": profiles,
        "active_profile_id": active_id,
        "usage": model_profiles.all_usage(),
        "usage_source": "local_estimate",
    }


@app.put("/model-profiles/active")
def model_profile_active(req: ActiveProfileRequest) -> dict[str, Any]:
    try:
        profile = model_profiles.set_active(req.profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "active_profile_id": profile["id"], "profile": profile}


@app.patch("/model-profiles/{profile_id}")
def model_profile_update(
    profile_id: str,
    req: ModelProfileUpdateRequest,
) -> dict[str, Any]:
    try:
        profile = model_profiles.update_profile(
            profile_id,
            req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "profile": profile}


@app.post("/model-profiles/{profile_id}/reset-usage")
def model_profile_reset_usage(profile_id: str) -> dict[str, Any]:
    try:
        usage = model_profiles.reset_usage(profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return {"ok": True, "usage": usage}


# --------------------------------------------------------------------------- #
# Unified conversation history
# --------------------------------------------------------------------------- #

class ConversationCreateRequest(BaseModel):
    id: str | None = None
    title: str = "Nova conversa"
    project_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    project_id: str | None = None
    tags: list[str] | None = None
    favorite: bool | None = None
    archived: bool | None = None


class ConversationMessageCreateRequest(BaseModel):
    role: str
    content: str
    parent_id: str | None = None
    branch_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageUpdateRequest(BaseModel):
    content: str | None = None
    metadata: dict[str, Any] | None = None


@app.get("/conversations")
def conversation_list(
    project_id: str | None = None,
    archived: bool | None = False,
    favorite: bool | None = None,
    tag: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    try:
        page = conversations.list_conversations(
            project_id=project_id,
            archived=archived,
            favorite=favorite,
            tag=tag,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **page}


@app.post("/conversations")
def conversation_create(req: ConversationCreateRequest) -> dict[str, Any]:
    try:
        item = conversations.create(
            title=req.title,
            project_id=req.project_id,
            tags=req.tags,
            favorite=req.favorite,
            conversation_id=req.id,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="A conversa já existe.")
    return {"ok": True, "conversation": item}


@app.get("/conversations/{conversation_id}")
def conversation_get(conversation_id: str) -> dict[str, Any]:
    item = conversations.get(conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True, "conversation": item}


@app.patch("/conversations/{conversation_id}")
def conversation_update(
    conversation_id: str,
    req: ConversationUpdateRequest,
) -> dict[str, Any]:
    try:
        item = conversations.update(
            conversation_id,
            req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True, "conversation": item}


@app.delete("/conversations/{conversation_id}")
def conversation_delete(
    conversation_id: str,
    permanent: bool = False,
) -> dict[str, Any]:
    if not conversations.delete(conversation_id, permanent=permanent):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True, "deleted": permanent, "archived": not permanent}


@app.get("/conversations/{conversation_id}/messages")
def conversation_message_list(
    conversation_id: str,
    branch_id: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    try:
        page = conversations.list_messages(
            conversation_id,
            branch_id=branch_id,
            limit=limit,
            cursor=cursor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **page}


@app.post("/conversations/{conversation_id}/messages")
def conversation_message_create(
    conversation_id: str,
    req: ConversationMessageCreateRequest,
) -> dict[str, Any]:
    try:
        item = conversations.add_message(
            conversation_id,
            **req.model_dump(),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "message": item}


@app.patch("/conversations/{conversation_id}/messages/{message_id}")
def conversation_message_update(
    conversation_id: str,
    message_id: str,
    req: ConversationMessageUpdateRequest,
) -> dict[str, Any]:
    try:
        item = conversations.update_message(
            conversation_id,
            message_id,
            req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "message": item}


@app.delete("/conversations/{conversation_id}/messages/{message_id}")
def conversation_message_delete(
    conversation_id: str,
    message_id: str,
) -> dict[str, Any]:
    if not conversations.delete_message(conversation_id, message_id):
        raise HTTPException(status_code=404, detail="Mensagem não encontrada.")
    return {"ok": True, "deleted": True}


# --------------------------------------------------------------------------- #
# Visual automations
# --------------------------------------------------------------------------- #

class AutomationCreateRequest(BaseModel):
    name: str
    trigger: dict[str, Any]
    action: dict[str, Any]
    enabled: bool = False
    require_approval: bool = True


class AutomationUpdateRequest(BaseModel):
    name: str | None = None
    trigger: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    enabled: bool | None = None
    require_approval: bool | None = None


class AutomationRunRequest(BaseModel):
    confirmed: bool = False


class AutomationEventRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


async def _automation_execute(
    action: dict[str, Any],
    confirmed: bool,
    request_id: str | None,
    force_approval: bool,
) -> dict[str, Any]:
    return await _execute_controlled(
        action,
        confirmed=confirmed,
        request_id=request_id,
        force_approval=force_approval,
    )


@app.get("/automations")
def automation_list(enabled: bool | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "automations": automations.list_automations(enabled=enabled),
        "capabilities": {
            "trigger_types": ["manual", "schedule", "file", "event", "condition"],
            "polling": True,
            "minimum_interval_seconds": 60,
            "condition_types": ["file_exists", "cpu_percent", "memory_percent"],
        },
    }


@app.post("/automations")
def automation_create(req: AutomationCreateRequest) -> dict[str, Any]:
    try:
        item = automations.create(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "automation": item}


@app.get("/automations/{automation_id}")
def automation_get(automation_id: str) -> dict[str, Any]:
    item = automations.get(automation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"ok": True, "automation": item}


@app.patch("/automations/{automation_id}")
def automation_update(
    automation_id: str,
    req: AutomationUpdateRequest,
) -> dict[str, Any]:
    try:
        item = automations.update(
            automation_id,
            req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "automation": item}


@app.delete("/automations/{automation_id}")
def automation_delete(automation_id: str) -> dict[str, Any]:
    if not automations.delete(automation_id):
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"ok": True, "deleted": True}


@app.post("/automations/{automation_id}/simulate")
async def automation_simulate(automation_id: str) -> dict[str, Any]:
    try:
        simulation = await automations.simulate(automation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"ok": True, "simulation": simulation}


@app.post("/automations/{automation_id}/run")
async def automation_run(
    automation_id: str,
    req: AutomationRunRequest,
) -> dict[str, Any]:
    try:
        run = await automations.run(
            automation_id,
            _automation_execute,
            confirmed=req.confirmed,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"ok": run["state"] != "failed", "run": run}


@app.get("/automations/{automation_id}/runs")
def automation_runs(automation_id: str, limit: int = 100) -> dict[str, Any]:
    try:
        runs = automations.list_runs(automation_id, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"ok": True, "runs": runs}


@app.post("/automations/events/{event_name}")
async def automation_event(
    event_name: str,
    req: AutomationEventRequest,
) -> dict[str, Any]:
    try:
        runs = await automations.emit_event(
            event_name,
            _automation_execute,
            payload=req.payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "runs": runs, "triggered": len(runs)}


@app.post("/command")
async def command(req: CommandRequest) -> dict[str, Any]:
    """Direct command dispatch (used by the developer terminal)."""
    # Translate the legacy server.ts command shape into an action.
    cmd, params = req.command, req.parameters
    action: dict[str, Any] | None = None
    if cmd == "list_workspace":
        try:
            listing = await workspace.tree(depth=1)
        except ValueError as exc:
            return {"status": "ERROR", "message": str(exc)}
        root_node = listing.get("tree") if isinstance(listing.get("tree"), dict) else {}
        children = root_node.get("children", []) if isinstance(root_node, dict) else []
        names = [
            str(item.get("path") or item.get("name") or "")
            for item in children
            if isinstance(item, dict)
        ]
        return {"status": "SUCCESS", "output": "\n".join(filter(None, names))}
    if cmd == "inspect_file":
        try:
            result = await workspace.read_file(str(params.get("filePath") or "package.json"))
        except ValueError as exc:
            return {"status": "ERROR", "message": str(exc)}
        if not result.get("ok"):
            return {
                "status": "ERROR",
                "message": str(result.get("error") or "Arquivo não encontrado."),
            }
        content = str(result.get("content") or "")
        if len(content) > 2_000_000:
            return {"status": "ERROR", "message": "Arquivo grande demais para inspeção direta."}
        return {"status": "SUCCESS", "output": content}
    if cmd == "run_diagnostic_script":
        snap = await os_control.system_snapshot()
        return {
            "status": "SUCCESS",
            "output": (
                f"[AETHER DIAGNÓSTICO]\n"
                f"CPU: {snap['cpu']:.1f}%\n"
                f"MEM: {snap['memory']:.1f}%\n"
                f"PROC: {snap['running_processes']}\n"
                f"Núcleo local operacional."
            ),
        }
    if cmd == "system_automation":
        action = {"type": "system_action", "target": params.get("action", "lock")}
    if action:
        return await run_action(action)
    return {"status": "ERROR", "message": f"Unknown command: {cmd}"}


# --------------------------------------------------------------------------- #
# TTS
# --------------------------------------------------------------------------- #

class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None


@app.get("/voices")
async def voices() -> dict[str, Any]:
    return {"voices": await tts.list_voices(), "default": settings.elevenlabs_voice_id}


@app.post("/tts")
async def synthesize(req: TTSRequest) -> Response:
    audio = await tts.synthesise(req.text, voice_id=req.voice_id)
    if not audio:
        raise HTTPException(status_code=400, detail="Empty text")
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/tts/stream")
async def synthesize_stream(req: TTSRequest) -> StreamingResponse:
    async def gen():
        async for chunk in tts.synthesise_stream(req.text, voice_id=req.voice_id):
            yield chunk
    return StreamingResponse(gen(), media_type="audio/mpeg")


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #

class FactRequest(BaseModel):
    key: str
    value: str


class PreferenceRequest(BaseModel):
    key: str
    value: str


class ProjectMemoryRequest(BaseModel):
    project_root: str
    key: str
    value: str
    kind: str = "note"


class MemoryCreateRequest(BaseModel):
    scope: str
    project_id: str | None = None
    kind: str
    key: str
    value: str
    enabled: bool = True


class MemoryUpdateRequest(BaseModel):
    key: str | None = None
    value: str | None = None
    kind: str | None = None
    enabled: bool | None = None


@app.get("/memory/short")
def memory_short(session_id: str = "default", limit: int = 30) -> dict[str, Any]:
    return {"history": memory.get_short_term_history(session_id, limit)}


@app.get("/memory/long")
def memory_long(limit: int = 200) -> dict[str, Any]:
    return {"history": memory.get_long_term(limit)}


@app.get("/memory/sessions")
def memory_sessions(limit: int = 50) -> dict[str, Any]:
    return {"ok": True, "sessions": memory.list_sessions(limit)}


@app.get("/memory/facts")
def memory_facts() -> dict[str, Any]:
    return {"facts": memory.get_facts()}


@app.post("/memory/facts")
def memory_facts_post(req: FactRequest) -> dict[str, Any]:
    try:
        memory.set_fact(req.key, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        memory.vector_store.upsert(f"fact:{req.key}", f"{req.key}: {req.value}", {"type": "fact"})
    except RuntimeError:
        pass
    return {"ok": True}


@app.get("/memory/preferences")
def memory_preferences() -> dict[str, Any]:
    return {"preferences": memory.get_preferences()}


@app.post("/memory/preferences")
def memory_preferences_post(req: PreferenceRequest) -> dict[str, Any]:
    try:
        memory.set_preference(req.key, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@app.get("/memory/overview")
def memory_overview(
    session_id: str = "default",
    project_root: str | None = None,
) -> dict[str, Any]:
    return {"ok": True, **memory.overview(session_id, project_root)}


@app.delete("/memory/turns/{turn_id}")
def memory_delete_turn(turn_id: str) -> dict[str, Any]:
    return {"ok": memory.delete_turn(turn_id)}


@app.delete("/memory/sessions/{session_id}")
def memory_clear_session(session_id: str) -> dict[str, Any]:
    return {"ok": True, "deleted": memory.clear_session(session_id)}


@app.delete("/memory/facts/{key}")
def memory_delete_fact(key: str) -> dict[str, Any]:
    return {"ok": memory.delete_fact(key)}


@app.delete("/memory/preferences/{key}")
def memory_delete_preference(key: str) -> dict[str, Any]:
    return {"ok": memory.delete_preference(key)}


@app.post("/memory/project")
def memory_project_set(req: ProjectMemoryRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "memory": memory.set_project_memory(
            req.project_root,
            req.key,
            req.value,
            req.kind,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/memory/project/{memory_id}")
def memory_project_delete(memory_id: str) -> dict[str, Any]:
    return {"ok": memory.delete_project_memory(memory_id)}


class RecallRequest(BaseModel):
    query: str
    n: int = 5


@app.post("/memory/recall")
def memory_recall(req: RecallRequest) -> dict[str, Any]:
    try:
        results = memory.vector_store.query(req.query, req.n)
        return {"ok": True, "results": results}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/memories")
def memories_list(
    scope: str | None = None,
    project_id: str | None = None,
    kind: str | None = None,
    enabled: bool | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    try:
        items = memory.list_memories(
            scope=scope,
            project_id=project_id,
            kind=kind,
            enabled=enabled,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "memories": items}


@app.post("/memories")
def memories_create(req: MemoryCreateRequest) -> dict[str, Any]:
    try:
        item = memory.create_memory(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "memory": item}


@app.patch("/memories/{memory_id}")
def memories_update(memory_id: str, req: MemoryUpdateRequest) -> dict[str, Any]:
    try:
        item = memory.update_memory(
            memory_id,
            **req.model_dump(exclude_none=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "memory": item}


@app.delete("/memories/{memory_id}")
def memories_delete(memory_id: str) -> dict[str, Any]:
    deleted = memory.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    return {"ok": True, "deleted": True}


# --------------------------------------------------------------------------- #
# Vision
# --------------------------------------------------------------------------- #

class VisionFrame(BaseModel):
    frame: str  # base64 JPEG (with or without data:image/jpeg;base64, prefix)


@app.post("/vision/analyze")
async def vision_analyze(req: VisionFrame) -> dict[str, Any]:
    if vision is None:
        raise HTTPException(status_code=503, detail="Instale requirements-vision.txt para ativar visão.")
    return await vision.analyze_frame(req.frame)


class EnrollFaceRequest(BaseModel):
    name: str
    frame: str
    confirmed: bool = False
    overwrite: bool = False


@app.post("/vision/enroll")
def vision_enroll(req: EnrollFaceRequest) -> dict[str, Any]:
    if vision is None:
        raise HTTPException(status_code=503, detail="Instale requirements-vision.txt para ativar visão.")
    if importlib.util.find_spec("face_recognition") is None:
        raise HTTPException(
            status_code=503,
            detail="O módulo opcional face-recognition não está disponível neste Python.",
        )
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Cadastrar dados biométricos exige confirmação.",
        )
    try:
        return vision.enroll_face(req.name, req.frame, overwrite=req.overwrite)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Reconhecimento facial não está disponível neste ambiente.",
        ) from exc


@app.get("/vision/faces")
def vision_faces() -> dict[str, Any]:
    if vision is None:
        raise HTTPException(status_code=503, detail="Instale requirements-vision.txt para ativar visão.")
    return {"enrolled": vision.list_enrolled_faces()}


# --------------------------------------------------------------------------- #
# Coding workspace
# --------------------------------------------------------------------------- #

class WorkspaceRootRequest(BaseModel):
    path: str
    confirmed: bool = False


class WorkspaceReadRequest(BaseModel):
    path: str


class WorkspaceWriteRequest(BaseModel):
    path: str
    content: str
    expected_sha256: str | None = None
    confirmed: bool = False


class WorkspaceCreateRequest(BaseModel):
    path: str
    kind: str = "file"
    confirmed: bool = False


class WorkspaceRenameRequest(BaseModel):
    path: str
    destination: str
    confirmed: bool = False


class WorkspaceDeleteRequest(BaseModel):
    path: str
    confirmed: bool = False


class WorkspaceSearchRequest(BaseModel):
    query: str


class WorkspaceTaskRequest(BaseModel):
    task_id: str
    confirmed: bool = False


class CodePlanRequest(BaseModel):
    instruction: str
    paths: list[str] = Field(default_factory=list)


class CodeApplyRequest(BaseModel):
    plan_id: str
    confirmed: bool = False
    paths: list[str] | None = None


class TaskCodeRequest(BaseModel):
    instruction: str
    paths: list[str] = Field(default_factory=list)
    session_id: str = "default"


class TaskValidationRequest(BaseModel):
    task_id: str
    confirmed: bool = False


class TaskControlRequest(BaseModel):
    action: str


class TaskApplyRequest(BaseModel):
    paths: list[str] | None = None
    confirmed: bool = False


@app.get("/workspace")
def workspace_get() -> dict[str, Any]:
    root = workspace.get_root()
    return {
        "ok": root is not None,
        "root": str(root) if root else None,
        "name": root.name if root else None,
    }


@app.post("/workspace")
async def workspace_set(req: WorkspaceRootRequest) -> Any:
    return await _execute_direct_action(
        {"type": "workspace_set", "target": req.path},
        confirmed=req.confirmed,
    )


@app.post("/workspace/inspect")
def workspace_inspect(req: WorkspaceRootRequest) -> dict[str, Any]:
    return workspace.inspect_root(req.path)


@app.get("/workspace/recent")
def workspace_recent() -> dict[str, Any]:
    return {"ok": True, "projects": workspace.recent_projects()}


@app.get("/workspace/tree")
async def workspace_tree(depth: int = 5) -> dict[str, Any]:
    try:
        return await workspace.tree(depth)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/workspace/read")
async def workspace_read(req: WorkspaceReadRequest) -> dict[str, Any]:
    try:
        return await workspace.read_file(req.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/workspace/write")
async def workspace_write(req: WorkspaceWriteRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "workspace_write",
            "target": req.path,
            "content": req.content,
            "expected_sha256": req.expected_sha256,
        },
        confirmed=req.confirmed,
    )


@app.post("/workspace/create")
async def workspace_create(req: WorkspaceCreateRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "workspace_create",
            "target": req.path,
            "kind": req.kind,
        },
        confirmed=req.confirmed,
    )


@app.post("/workspace/rename")
async def workspace_rename(req: WorkspaceRenameRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "workspace_rename",
            "target": req.path,
            "destination": req.destination,
        },
        confirmed=req.confirmed,
    )


@app.post("/workspace/delete")
async def workspace_delete(req: WorkspaceDeleteRequest) -> Any:
    return await _execute_direct_action(
        {"type": "workspace_delete", "target": req.path},
        confirmed=req.confirmed,
    )


@app.post("/workspace/search")
async def workspace_search(req: WorkspaceSearchRequest) -> dict[str, Any]:
    try:
        return await workspace.search(req.query)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/workspace/tasks")
def workspace_tasks() -> dict[str, Any]:
    try:
        return {"ok": True, "tasks": workspace.available_tasks()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/workspace/run")
async def workspace_run(req: WorkspaceTaskRequest) -> Any:
    return await _execute_direct_action(
        {"type": "workspace_run", "target": req.task_id},
        confirmed=req.confirmed,
    )


@app.post("/code/plan")
async def code_plan(req: CodePlanRequest) -> dict[str, Any]:
    return await code_agent.plan(req.instruction, req.paths)


@app.post("/code/apply")
async def code_apply(req: CodeApplyRequest) -> dict[str, Any]:
    return await code_agent.apply(req.plan_id, req.confirmed, req.paths)


@app.get("/code/history")
def code_history() -> dict[str, Any]:
    return {"ok": True, "history": code_agent.history()}


@app.post("/code/checkpoints/{checkpoint_id}/undo")
async def code_undo(checkpoint_id: str, confirmed: bool = False) -> dict[str, Any]:
    return await code_agent.undo(checkpoint_id, confirmed)


@app.post("/tasks/code")
async def task_code(req: TaskCodeRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "task": task_manager.create_code_task(
            req.instruction,
            req.paths,
            req.session_id,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/tasks/validation")
async def task_validation(req: TaskValidationRequest) -> dict[str, Any]:
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Executar uma validação do projeto exige confirmação.",
        )
    try:
        return {"ok": True, "task": task_manager.create_validation_task(req.task_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/tasks")
def tasks_list(limit: int = 30) -> dict[str, Any]:
    return {"ok": True, "tasks": task_manager.list_tasks(limit)}


@app.get("/tasks/{task_id}")
def task_get(task_id: str) -> dict[str, Any]:
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return {"ok": True, "task": task}


@app.post("/tasks/{task_id}/control")
def task_control(task_id: str, req: TaskControlRequest) -> dict[str, Any]:
    return task_manager.control(task_id, req.action)


@app.post("/tasks/{task_id}/apply")
async def task_apply(task_id: str, req: TaskApplyRequest) -> dict[str, Any]:
    return await task_manager.apply_task(task_id, req.paths, req.confirmed)


@app.post("/tasks/{task_id}/reject")
def task_reject(task_id: str) -> dict[str, Any]:
    return task_manager.reject_task(task_id)


# --------------------------------------------------------------------------- #
# Skills
# --------------------------------------------------------------------------- #

class SkillPayload(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    rules: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    knowledge_files: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    priority: int = 50
    enabled: bool = True
    category: str = "Geral"
    scope: str = "global"
    project_root: str | None = None


class SkillTestRequest(BaseModel):
    sample: str
    project_root: str | None = None


class SkillImportRequest(BaseModel):
    pack: dict[str, Any]


@app.get("/skills")
def skill_list(
    project_root: str | None = None,
    include_disabled: bool = True,
) -> dict[str, Any]:
    return {
        "ok": True,
        "skills": skills.list_skills(project_root, include_disabled),
    }


@app.post("/skills")
def skill_create(req: SkillPayload) -> dict[str, Any]:
    try:
        return {"ok": True, "skill": skills.create_skill(req.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/skills/export")
def skill_export(ids: str | None = None) -> dict[str, Any]:
    skill_ids = [item for item in (ids or "").split(",") if item]
    return {"ok": True, "pack": skills.export_skills(skill_ids or None)}


@app.post("/skills/import")
def skill_import(req: SkillImportRequest) -> dict[str, Any]:
    try:
        return {"ok": True, "skills": skills.import_skills(req.pack)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/skills/{skill_id}")
def skill_get(skill_id: str) -> dict[str, Any]:
    skill = skills.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill não encontrada.")
    return {"ok": True, "skill": skill, "revisions": skills.revisions(skill_id)}


@app.put("/skills/{skill_id}")
def skill_update(skill_id: str, req: SkillPayload) -> dict[str, Any]:
    try:
        return {"ok": True, "skill": skills.update_skill(skill_id, req.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/skills/{skill_id}")
def skill_delete(skill_id: str, confirmed: bool = False) -> dict[str, Any]:
    return skills.delete_skill(skill_id, confirmed)


@app.post("/skills/{skill_id}/duplicate")
def skill_duplicate(skill_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "skill": skills.duplicate_skill(skill_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/skills/{skill_id}/test")
def skill_test(skill_id: str, req: SkillTestRequest) -> dict[str, Any]:
    try:
        return skills.test_skill(skill_id, req.sample, req.project_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/skills/{skill_id}/restore/{revision_id}")
def skill_restore(skill_id: str, revision_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "skill": skills.restore_revision(skill_id, revision_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# --------------------------------------------------------------------------- #
# OS control
# --------------------------------------------------------------------------- #

@app.get("/os/apps")
async def os_apps() -> dict[str, Any]:
    apps = await asyncio.to_thread(os_control.list_installed_apps)
    return {"apps": apps}


@app.get("/os/processes")
async def os_processes(filter: str | None = None) -> dict[str, Any]:
    return {"processes": await os_control.list_processes(filter)}


@app.post("/os/processes/kill")
async def os_kill(
    name: str,
    confirm: bool = False,
) -> Any:
    return await _execute_direct_action(
        {"type": "kill_app", "target": name},
        confirmed=confirm,
    )


@app.post("/os/file")
async def os_file(req: FileRequest) -> Any:
    action = req.action.strip().lower()
    if action not in {"copy", "move", "rename", "delete"}:
        raise HTTPException(status_code=400, detail="Operação de arquivo inválida.")
    return await _execute_direct_action(
        {
            "type": "file_operation",
            "operation": action,
            "source": req.src,
            "destination": req.dst,
        },
        confirmed=req.confirm,
    )


@app.get("/os/file/list")
async def os_file_list(path: str) -> dict[str, Any]:
    return await os_control.list_directory(path)


@app.post("/os/volume")
async def os_volume(
    level: int,
    confirmed: bool = False,
) -> Any:
    return await _execute_direct_action(
        {"type": "set_volume", "target": level},
        confirmed=confirmed,
    )


@app.post("/os/brightness")
async def os_brightness(
    level: int,
    confirmed: bool = False,
) -> Any:
    return await _execute_direct_action(
        {"type": "set_brightness", "target": level},
        confirmed=confirmed,
    )


@app.post("/os/media")
async def os_media(
    command: str,
    confirmed: bool = False,
) -> Any:
    return await _execute_direct_action(
        {"type": "media_command", "target": command},
        confirmed=confirmed,
    )


class SystemActionRequest(BaseModel):
    action: str
    confirmed: bool = False


@app.post("/os/system")
async def os_system(req: SystemActionRequest) -> Any:
    return await _execute_direct_action(
        {"type": "system_action", "target": req.action},
        confirmed=req.confirmed,
    )


class OpenAppRequest(BaseModel):
    name: str
    confirmed: bool = False


class OpenPathRequest(BaseModel):
    path: str
    confirmed: bool = False


class OpenUrlRequest(BaseModel):
    url: str
    confirmed: bool = False


@app.post("/os/app/open")
async def os_open_app(req: OpenAppRequest) -> Any:
    return await _execute_direct_action(
        {"type": "open_app", "target": req.name},
        confirmed=req.confirmed,
    )


@app.post("/os/path/open")
async def os_open_path(req: OpenPathRequest) -> Any:
    return await _execute_direct_action(
        {"type": "open_path", "target": req.path},
        confirmed=req.confirmed,
    )


@app.post("/os/url/open")
async def os_open_url(req: OpenUrlRequest) -> Any:
    return await _execute_direct_action(
        {"type": "open_url", "target": req.url},
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# WebSocket — live HUD telemetry
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# File organization
# --------------------------------------------------------------------------- #

class OrganizeRequest(BaseModel):
    folder: str = "~/Downloads"
    by_type: bool = True
    by_date: bool = False
    dry_run: bool = True
    confirmed: bool = False


class CleanTempRequest(BaseModel):
    folder: str = "~/Downloads"
    days_old: int = 30
    dry_run: bool = True
    confirmed: bool = False


class UndoOrganizeRequest(BaseModel):
    folder: str
    confirmed: bool = False


@app.post("/files/organize")
async def files_organize(req: OrganizeRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "organize_files",
            "target": req.folder,
            "by_type": req.by_type,
            "by_date": req.by_date,
            "dry_run": req.dry_run,
        },
        confirmed=req.confirmed,
    )


@app.post("/files/clean-temp")
async def files_clean_temp(req: CleanTempRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "clean_temp_files",
            "target": req.folder,
            "days_old": req.days_old,
            "dry_run": req.dry_run,
        },
        confirmed=req.confirmed,
    )


@app.post("/files/undo-organize")
async def files_undo_organize(req: UndoOrganizeRequest) -> Any:
    return await _execute_direct_action(
        {"type": "undo_organize_files", "target": req.folder},
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# VLM (Vision Language Model) analysis
# --------------------------------------------------------------------------- #

class VLMRequest(BaseModel):
    image: str = Field(min_length=4, max_length=20 * 1024 * 1024)
    prompt: str = Field(
        default="Descreva detalhadamente o que você vê nesta imagem.",
        min_length=1,
        max_length=10_000,
    )
    mime_type: str = Field(default="image/jpeg", max_length=80)


@app.post("/vlm/analyze")
async def vlm_analyze(req: VLMRequest) -> dict[str, Any]:
    """Analyze an image using the configured VLM provider (GLM-4V, Gemini, etc.)."""
    try:
        encoded = req.image.split(",", 1)[-1].strip()
        if not encoded:
            raise HTTPException(status_code=400, detail="Imagem vazia.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Imagem base64 inválida.") from exc
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="A imagem excede o limite de 15 MB.")

        prefix_mime = ""
        if req.image.startswith("data:") and "," in req.image:
            prefix_mime = req.image[5:].split(";", 1)[0].strip().lower()
        mime_type = prefix_mime or req.mime_type.strip().lower()
        allowed_mime_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if mime_type not in allowed_mime_types:
            raise HTTPException(status_code=400, detail="Formato de imagem não permitido.")

        result = await llm_module.analyze_image_vlm(req.image, req.prompt, mime_type)
        if result:
            return {"ok": True, "description": result}
        return {"ok": False, "error": "VLM não configurado ou retornou vazio."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# --------------------------------------------------------------------------- #
# Web Search
# --------------------------------------------------------------------------- #

class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class WebFetchRequest(BaseModel):
    url: str


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1_000)
    max_results: int = Field(default=5, ge=1, le=8)
    max_chars_per_source: int = Field(default=30_000, ge=1_000, le=50_000)


@app.post("/web/search")
async def web_search_endpoint(req: WebSearchRequest) -> dict[str, Any]:
    return {"ok": True, **await web_search.search_and_summarize(req.query, req.max_results)}


@app.post("/web/fetch")
async def web_fetch_endpoint(req: WebFetchRequest) -> dict[str, Any]:
    text = await web_search.fetch_page_text(req.url)
    if text:
        return {"ok": True, "url": req.url, "text": text}
    raise HTTPException(status_code=502, detail="Não foi possível acessar a URL.")


@app.post("/research")
async def professional_research(req: ResearchRequest) -> dict[str, Any]:
    try:
        return await web_search.research(
            req.query,
            max_results=req.max_results,
            max_chars_per_source=req.max_chars_per_source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------- #
# Projects and document library
# --------------------------------------------------------------------------- #

class DocumentExtractRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    mime_type: str | None = Field(default=None, max_length=160)
    data_base64: str = Field(
        min_length=4,
        max_length=project_library.MAX_BASE64_CHARS,
    )


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    instructions: str = ""
    root_path: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    root_path: str | None = None
    archived: bool | None = None


class DocumentImportRequest(BaseModel):
    name: str | None = None
    path: str | None = None
    data_base64: str | None = Field(
        default=None,
        max_length=project_library.MAX_BASE64_CHARS,
    )
    mime_type: str | None = None
    source_url: str | None = None


class FolderImportRequest(BaseModel):
    path: str


class ProjectSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=8, ge=1, le=30)


@app.post("/documents/extract")
def document_extract(req: DocumentExtractRequest) -> dict[str, Any]:
    encoded = req.data_base64.split(",", 1)[-1].strip()
    if not encoded or len(encoded) > (project_library.MAX_DOCUMENT_BYTES * 4 // 3 + 16):
        raise HTTPException(
            status_code=413,
            detail="O documento excede o limite de 20 MB.",
        )
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Conteúdo base64 inválido.") from exc
    if len(raw) > project_library.MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="O documento excede o limite de 20 MB.",
        )
    try:
        text, sections, metadata = project_library.extract(
            raw,
            req.name,
            req.mime_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "name": Path(req.name).name,
        "mime_type": req.mime_type,
        "text": text,
        "metadata": {
            **metadata,
            "bytes": len(raw),
            "text_chars": len(text),
        },
        "sections": sections,
        "persisted": False,
    }


@app.get("/projects/capabilities")
def project_capabilities() -> dict[str, Any]:
    return {"ok": True, **project_library.capabilities()}


@app.get("/projects")
def project_list(
    archived: bool | None = False,
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "ok": True,
        "projects": project_library.list_projects(
            archived=archived,
            limit=limit,
        ),
    }


@app.post("/projects")
def project_create(req: ProjectCreateRequest) -> dict[str, Any]:
    try:
        item = project_library.create_project(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "project": item}


@app.get("/projects/{project_id}")
def project_get(project_id: str) -> dict[str, Any]:
    item = project_library.get_project(project_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"ok": True, "project": item}


@app.patch("/projects/{project_id}")
def project_update(project_id: str, req: ProjectUpdateRequest) -> dict[str, Any]:
    try:
        item = project_library.update_project(
            project_id,
            req.model_dump(exclude_unset=True),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "project": item}


@app.delete("/projects/{project_id}")
def project_delete(project_id: str, permanent: bool = False) -> dict[str, Any]:
    if not permanent:
        try:
            project = project_library.update_project(
                project_id,
                {"archived": True},
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="Projeto não encontrado.")
        return {"ok": True, "deleted": False, "archived": True, "project": project}
    if not project_library.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"ok": True, "deleted": True, "archived": False}


@app.get("/projects/{project_id}/documents")
def project_documents(project_id: str, limit: int = 500) -> dict[str, Any]:
    try:
        documents = project_library.list_documents(project_id, limit=limit)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return {"ok": True, "documents": documents}


@app.post("/projects/{project_id}/documents/import")
async def project_document_import(
    project_id: str,
    req: DocumentImportRequest,
) -> dict[str, Any]:
    supplied = sum(bool(value) for value in (req.path, req.data_base64, req.source_url))
    if supplied != 1:
        raise HTTPException(
            status_code=400,
            detail="Envie exatamente um entre path, data_base64 ou source_url.",
        )
    try:
        if req.data_base64:
            document = project_library.import_base64(
                project_id,
                data_base64=req.data_base64,
                name=req.name or "documento",
                mime_type=req.mime_type,
            )
        elif req.path:
            document = project_library.import_path(
                project_id,
                req.path,
                name=req.name,
            )
        else:
            details = await web_search.fetch_page_details(str(req.source_url))
            if not details.get("ok"):
                raise ValueError(
                    str(details.get("error") or "Não foi possível abrir a página.")
                )
            document = project_library.import_page_text(
                project_id,
                url=str(details["url"]),
                title=req.name or str(details.get("title") or "Página"),
                text=str(details.get("text") or ""),
            )
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "document": document}


@app.post("/projects/{project_id}/documents/import-folder")
def project_folder_import(
    project_id: str,
    req: FolderImportRequest,
) -> dict[str, Any]:
    try:
        return project_library.import_folder(project_id, req.path)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/projects/{project_id}/documents/{document_id}")
def project_document_get(project_id: str, document_id: str) -> dict[str, Any]:
    document = project_library.get_document(project_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {"ok": True, "document": document}


@app.delete("/projects/{project_id}/documents/{document_id}")
def project_document_delete(project_id: str, document_id: str) -> dict[str, Any]:
    if not project_library.delete_document(project_id, document_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return {"ok": True, "deleted": True}


@app.post("/projects/{project_id}/search")
def project_search(project_id: str, req: ProjectSearchRequest) -> dict[str, Any]:
    try:
        return project_library.search(project_id, req.query, limit=req.limit)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


# --------------------------------------------------------------------------- #
# Git Integration
# --------------------------------------------------------------------------- #

class GitPathRequest(BaseModel):
    path: str


class GitCommitRequest(BaseModel):
    path: str
    message: str
    confirmed: bool = False


class GitBranchRequest(BaseModel):
    path: str
    name: str
    base: str | None = None
    confirmed: bool = False


class GitRemoteRequest(BaseModel):
    path: str
    remote: str = "origin"
    branch: str | None = None
    confirmed: bool = False


class GitMergeRequest(BaseModel):
    path: str
    branch: str
    confirmed: bool = False


@app.post("/git/status")
async def git_status(req: GitPathRequest) -> Any:
    return await _execute_direct_action(
        {"type": "git_status", "target": req.path},
    )


@app.post("/git/log")
async def git_log(req: GitPathRequest) -> Any:
    return await _execute_direct_action(
        {"type": "git_log", "target": req.path},
    )


@app.post("/git/diff")
async def git_diff(req: GitPathRequest) -> Any:
    return await _execute_direct_action(
        {"type": "git_diff", "target": req.path},
    )


@app.post("/git/commit")
async def git_commit(req: GitCommitRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_commit",
            "target": req.path,
            "message": req.message,
        },
        confirmed=req.confirmed,
    )


@app.post("/git/push")
async def git_push(req: GitRemoteRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_push",
            "target": req.path,
            "remote": req.remote,
            "branch": req.branch,
        },
        confirmed=req.confirmed,
    )


@app.post("/git/pull")
async def git_pull(req: GitRemoteRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_pull",
            "target": req.path,
            "remote": req.remote,
            "branch": req.branch,
        },
        confirmed=req.confirmed,
    )


@app.post("/git/branches")
async def git_branches(req: GitPathRequest) -> Any:
    return await _execute_direct_action(
        {"type": "git_branch", "target": req.path},
    )


@app.post("/git/branch/create")
async def git_branch_create(req: GitBranchRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_branch_create",
            "target": req.path,
            "name": req.name,
            "base": req.base,
        },
        confirmed=req.confirmed,
    )


@app.post("/git/branch/checkout")
async def git_branch_checkout(req: GitBranchRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_branch_checkout",
            "target": req.path,
            "name": req.name,
        },
        confirmed=req.confirmed,
    )


@app.post("/git/merge")
async def git_merge(req: GitMergeRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "git_merge",
            "target": req.path,
            "branch": req.branch,
        },
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #

class EmailListRequest(BaseModel):
    max: int = 10
    query: str = ""


class EmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str
    confirmed: bool = False


@app.get("/email/list")
async def email_list(max: int = 10, query: str = "") -> Any:
    return await _execute_direct_action(
        {"type": "email_list", "max": max, "query": query},
    )


@app.post("/email/send")
async def email_send(req: EmailSendRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "email_send",
            "to": req.to,
            "subject": req.subject,
            "body": req.body,
        },
        confirmed=req.confirmed,
    )


@app.post("/email/search")
async def email_search(req: EmailListRequest) -> Any:
    return await _execute_direct_action(
        {"type": "email_search", "query": req.query, "max": req.max},
    )


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #

class CalendarEventRequest(BaseModel):
    summary: str
    start_time: str
    end_time: str
    description: str = ""
    location: str = ""
    time_zone: str | None = None
    confirmed: bool = False


@app.get("/calendar/events")
async def calendar_events(max_results: int = 10) -> Any:
    return await _execute_direct_action(
        {"type": "calendar_list", "max": max_results},
    )


@app.post("/calendar/events")
async def calendar_create(req: CalendarEventRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "calendar_create",
            "summary": req.summary,
            "start_time": req.start_time,
            "end_time": req.end_time,
            "description": req.description,
            "location": req.location,
            "time_zone": req.time_zone,
        },
        confirmed=req.confirmed,
    )


@app.delete("/calendar/events/{event_id}")
async def calendar_delete(event_id: str, confirmed: bool = False) -> Any:
    return await _execute_direct_action(
        {"type": "calendar_delete", "event_id": event_id},
        confirmed=confirmed,
    )


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #

class WeatherRequest(BaseModel):
    city: str = ""


@app.post("/weather/current")
async def weather_current(req: WeatherRequest) -> dict[str, Any]:
    return await weather.get_weather(req.city)


@app.post("/weather/forecast")
async def weather_forecast(req: WeatherRequest) -> dict[str, Any]:
    return await weather.get_forecast(req.city)


# --------------------------------------------------------------------------- #
# PDF Processing
# --------------------------------------------------------------------------- #

class PDFRequest(BaseModel):
    path: str


class PDFUploadRequest(BaseModel):
    name: str = Field(default="documento.pdf", min_length=1, max_length=240)
    data_base64: str = Field(min_length=4, max_length=14 * 1024 * 1024)


@app.post("/pdf/text")
async def pdf_text(req: PDFRequest) -> dict[str, Any]:
    return await pdf_processor.extract_text(req.path)


@app.post("/pdf/upload-text")
async def pdf_upload_text(req: PDFUploadRequest) -> dict[str, Any]:
    return await pdf_processor.extract_text_bytes(req.data_base64, req.name)


@app.post("/pdf/tables")
async def pdf_tables(req: PDFRequest) -> dict[str, Any]:
    return await pdf_processor.extract_tables(req.path)


@app.post("/pdf/extract")
async def pdf_extract(req: PDFRequest) -> dict[str, Any]:
    return await pdf_processor.extract_text(req.path)


# --------------------------------------------------------------------------- #
# File Crypto
# --------------------------------------------------------------------------- #

class CryptoFileRequest(BaseModel):
    path: str
    confirmed: bool = False
    overwrite: bool = False


class CryptoTextRequest(BaseModel):
    text: str
    confirmed: bool = False


class CryptoDecryptRequest(BaseModel):
    encrypted_b64: str
    confirmed: bool = False


@app.post("/crypto/encrypt")
async def crypto_encrypt(req: CryptoFileRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "crypto_encrypt",
            "target": req.path,
            "overwrite": req.overwrite,
        },
        confirmed=req.confirmed,
    )


@app.post("/crypto/decrypt")
async def crypto_decrypt(req: CryptoFileRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "crypto_decrypt",
            "target": req.path,
            "overwrite": req.overwrite,
        },
        confirmed=req.confirmed,
    )


@app.post("/crypto/encrypt-text")
async def crypto_encrypt_text(req: CryptoTextRequest) -> Any:
    return await _execute_direct_action(
        {"type": "crypto_encrypt_text", "text": req.text},
        confirmed=req.confirmed,
    )


@app.post("/crypto/decrypt-text")
async def crypto_decrypt_text(req: CryptoDecryptRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "crypto_decrypt_text",
            "encrypted_b64": req.encrypted_b64,
        },
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# Backup
# --------------------------------------------------------------------------- #

class BackupCreateRequest(BaseModel):
    path: str
    confirmed: bool = False


class BackupRestoreRequest(BaseModel):
    backup_path: str
    target_dir: str | None = None
    confirmed: bool = False
    overwrite: bool = False


@app.post("/backup/create")
async def backup_create(req: BackupCreateRequest) -> Any:
    return await _execute_direct_action(
        {"type": "backup_create", "target": req.path},
        confirmed=req.confirmed,
    )


@app.get("/backup/list")
async def backup_list() -> Any:
    return await _execute_direct_action({"type": "backup_list"})


@app.post("/backup/restore")
async def backup_restore(req: BackupRestoreRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "backup_restore",
            "target": req.backup_path,
            "target_dir": req.target_dir,
            "overwrite": req.overwrite,
        },
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# Plugin System
# --------------------------------------------------------------------------- #

class PluginInstallRequest(BaseModel):
    path: str
    confirmed: bool = False


class PluginRunRequest(BaseModel):
    plugin_id: str
    action: str = "run"
    params: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


@app.get("/plugins")
async def plugin_list() -> Any:
    return await _execute_direct_action({"type": "plugin_list"})


@app.post("/plugins/load/{plugin_id}")
async def plugin_load(plugin_id: str, confirmed: bool = False) -> Any:
    return await _execute_direct_action(
        {"type": "plugin_load", "target": plugin_id},
        confirmed=confirmed,
    )


@app.post("/plugins/unload/{plugin_id}")
async def plugin_unload(plugin_id: str, confirmed: bool = False) -> Any:
    return await _execute_direct_action(
        {"type": "plugin_unload", "target": plugin_id},
        confirmed=confirmed,
    )


@app.post("/plugins/reload/{plugin_id}")
async def plugin_reload(plugin_id: str, confirmed: bool = False) -> Any:
    return await _execute_direct_action(
        {"type": "plugin_reload", "target": plugin_id},
        confirmed=confirmed,
    )


@app.post("/plugins/install")
async def plugin_install(req: PluginInstallRequest) -> Any:
    return await _execute_direct_action(
        {"type": "plugin_install", "target": req.path},
        confirmed=req.confirmed,
    )


@app.post("/plugins/run")
async def plugin_run(req: PluginRunRequest) -> Any:
    return await _execute_direct_action(
        {
            "type": "plugin_run",
            "target": req.plugin_id,
            "plugin_action": req.action,
            "params": req.params,
        },
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# Browser Automation
# --------------------------------------------------------------------------- #

class BrowserNavigateRequest(BaseModel):
    url: str
    headless: bool = True
    confirmed: bool = False


class BrowserClickRequest(BaseModel):
    url: str
    selector: str
    confirmed: bool = False


class BrowserFillRequest(BaseModel):
    url: str
    selector: str
    value: str
    confirmed: bool = False


@app.get("/browser/status")
def browser_automation_status() -> dict[str, Any]:
    return browser_agent.status()


@app.post("/browser/navigate")
async def browser_navigate(req: BrowserNavigateRequest) -> Any:
    if not browser_agent.NETWORK_AUTOMATION_ENABLED:
        return await browser_agent.navigate(req.url, headless=req.headless)
    return await _execute_direct_action(
        {
            "type": "browser_navigate",
            "target": req.url,
            "headless": req.headless,
        },
        confirmed=req.confirmed,
    )


@app.post("/browser/screenshot")
async def browser_screenshot(req: BrowserNavigateRequest) -> Any:
    if not browser_agent.NETWORK_AUTOMATION_ENABLED:
        return await browser_agent.screenshot(req.url, headless=req.headless)
    return await _execute_direct_action(
        {
            "type": "browser_screenshot",
            "target": req.url,
            "headless": req.headless,
        },
        confirmed=req.confirmed,
    )


@app.post("/browser/click")
async def browser_click(req: BrowserClickRequest) -> Any:
    if not browser_agent.NETWORK_AUTOMATION_ENABLED:
        return await browser_agent.click_element(req.url, req.selector)
    return await _execute_direct_action(
        {
            "type": "browser_click",
            "target": req.url,
            "selector": req.selector,
        },
        confirmed=req.confirmed,
    )


@app.post("/browser/fill")
async def browser_fill(req: BrowserFillRequest) -> Any:
    if not browser_agent.NETWORK_AUTOMATION_ENABLED:
        return await browser_agent.fill_form(req.url, req.selector, req.value)
    return await _execute_direct_action(
        {
            "type": "browser_fill",
            "target": req.url,
            "selector": req.selector,
            "value": req.value,
        },
        confirmed=req.confirmed,
    )


# --------------------------------------------------------------------------- #
# LLM Provider info
# --------------------------------------------------------------------------- #

@app.get("/llm/provider")
def llm_provider_info() -> dict[str, Any]:
    from .llm_providers import get_provider
    provider = get_provider()
    return {
        "ok": provider is not None,
        "provider": settings.llm_provider,
        "model": settings.llm_model or settings.agent_orchestrator_model,
        "configured": provider is not None,
    }


# --------------------------------------------------------------------------- #
# Aether 4.3 — Personal Control, Trust and Quality
# --------------------------------------------------------------------------- #

@app.get("/experience-profiles")
def experience_profile_list() -> dict[str, Any]:
    active = experience_profiles.get_active()
    return {
        "ok": True,
        "profiles": experience_profiles.list_profiles(),
        "active_profile_id": active["id"],
        "active": active,
    }


@app.post("/experience-profiles")
def experience_profile_create(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        profile = experience_profiles.create_profile(
            name=str(payload.get("name") or ""),
            kind=str(payload.get("kind") or "custom"),
            home=payload.get("home") if isinstance(payload.get("home"), dict) else None,
            reading=(
                payload.get("reading")
                if isinstance(payload.get("reading"), dict)
                else None
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "profile": profile}


@app.patch("/experience-profiles/{profile_id}")
def experience_profile_update(
    profile_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        profile = experience_profiles.update_profile(profile_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil de uso não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "profile": profile}


@app.put("/experience-profiles/active")
def experience_profile_activate(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        profile = experience_profiles.set_active(
            str(payload.get("profile_id") or payload.get("id") or "")
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil de uso não encontrado.")
    return {"ok": True, "profile": profile}


@app.delete("/experience-profiles/{profile_id}")
def experience_profile_delete(profile_id: str) -> dict[str, Any]:
    try:
        removed = experience_profiles.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="Perfil de uso não encontrado.")
    return {"ok": True, "deleted": profile_id}


@app.get("/connections")
def connection_overview() -> dict[str, Any]:
    return connections.overview()


@app.post("/connections/test")
async def connection_test(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    profile_id = str(payload.get("profile_id") or "")
    try:
        return await connections.test(profile_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil de modelo não encontrado.")


@app.get("/privacy")
def privacy_get(
    conversation_id: str | None = None,
) -> dict[str, Any]:
    state = privacy_control.get_state()
    effective = privacy_control.effective_mode(conversation_id)
    return {
        "ok": True,
        "mode": effective["mode"],
        "privacy": effective,
        "state": state,
        "effective": effective,
        "flows": (
            privacy_control.list_flows(conversation_id, limit=100)
            if conversation_id
            else []
        ),
        "modes": [
            {
                "id": "standard",
                "name": "Padrão",
                "description": "Permite destinos externos validados.",
            },
            {
                "id": "local_only",
                "name": "100% local",
                "description": "Bloqueia qualquer destino que não seja loopback.",
            },
        ],
    }


@app.put("/privacy")
def privacy_set(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        state = privacy_control.set_mode(str(payload.get("mode") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "mode": state["mode"], "privacy": state, "state": state}


@app.put("/privacy/conversations/{conversation_id}")
def privacy_conversation_set(
    conversation_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    if conversations.get(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    try:
        state = privacy_control.set_conversation_mode(
            conversation_id,
            str(payload.get("mode") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "state": state}


@app.delete("/privacy/conversations/{conversation_id}")
def privacy_conversation_delete(conversation_id: str) -> dict[str, Any]:
    return {
        "ok": privacy_control.delete_conversation_mode(conversation_id),
        "conversation_id": conversation_id,
    }


@app.get("/privacy/map")
def privacy_map(
    conversation_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "map": privacy_control.privacy_map(conversation_id, limit=limit),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/audit/search")
def audit_search(
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    project_id: str | None = None,
    resource: str | None = None,
    site: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            **audit_integrity.search(
                since=since,
                until=until,
                kind=kind,
                project_id=project_id,
                resource=resource,
                site=site,
                recipient=recipient,
                query=query,
                limit=limit,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/audit/integrity")
def audit_chain_integrity() -> dict[str, Any]:
    return {"ok": True, "integrity": audit_integrity.verify_chain()}


@app.get("/audit/report")
def audit_report(
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    project_id: str | None = None,
    resource: str | None = None,
    site: str | None = None,
    recipient: str | None = None,
    query: str | None = None,
    limit: int = 200,
    format: str = "markdown",
) -> Response:
    try:
        if format.casefold() == "json":
            payload = {
                "format": "aether-audit-report-v1",
                "app_version": APP_VERSION,
                "integrity": audit_integrity.verify_chain(),
                "search": audit_integrity.search(
                    since=since,
                    until=until,
                    kind=kind,
                    project_id=project_id,
                    resource=resource,
                    site=site,
                    recipient=recipient,
                    query=query,
                    limit=limit,
                ),
            }
            return JSONResponse(
                payload,
                headers={
                    "Content-Disposition": 'attachment; filename="aether-audit-report.json"'
                },
            )
        markdown = audit_integrity.markdown_report(
            since=since,
            until=until,
            kind=kind,
            project_id=project_id,
            resource=resource,
            site=site,
            recipient=recipient,
            query=query,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="aether-audit-report.md"'
        },
    )


@app.post("/responses/verify")
def response_verify(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return response_verifier.verify(
            str(payload.get("answer") or payload.get("text") or ""),
            payload.get("sources") if isinstance(payload.get("sources"), list) else [],
            require_independent_sources=payload.get(
                "require_independent_sources", True
            ) is not False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/model-profiles")
def model_profile_create(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return {"ok": True, "profile": model_profiles.create_profile(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/model-profiles/{profile_id}/clone")
def model_profile_clone(
    profile_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        profile = model_profiles.clone_profile(
            profile_id,
            name=str(payload.get("name") or "") or None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "profile": profile}


@app.delete("/model-profiles/{profile_id}")
def model_profile_delete(profile_id: str) -> dict[str, Any]:
    try:
        removed = model_profiles.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return {"ok": True, "deleted": profile_id}


def _estimated_candidate_cost(
    profile: dict[str, Any],
    input_tokens: int,
    output_tokens: int,
) -> float:
    return round(
        (
            input_tokens * float(profile.get("cost_input_per_million") or 0)
            + output_tokens * float(profile.get("cost_output_per_million") or 0)
        )
        / 1_000_000,
        8,
    )


async def _model_lab_candidate(
    prepared: dict[str, Any],
    profile_id: str,
    prompt: str,
    candidate_id: str,
) -> dict[str, Any]:
    profile = model_profiles.get_profile(profile_id)
    if profile is None:
        return {
            "id": candidate_id,
            "profile_id": profile_id,
            "text": "",
            "error": "Perfil não encontrado.",
            "metrics": {},
        }
    started = time.perf_counter()
    first_token_ms: float | None = None
    first_token_measured = False
    chunks: list[str] = []
    error: str | None = None
    context = dict(prepared["llm_context"])
    context["model_profile_id"] = profile_id
    try:
        async for event in llm_module.stream_respond(**context):
            event_type = event.get("type")
            if event_type == "token":
                if first_token_ms is None:
                    first_token_ms = round(
                        (time.perf_counter() - started) * 1_000,
                        2,
                    )
                    first_token_measured = True
                chunks.append(str(event.get("delta") or ""))
            elif event_type in {"buffered_result", "stream_end"}:
                chunks = [str(event.get("text") or "")]
            elif event_type == "unavailable":
                error = "O perfil não está disponível."
    except Exception:
        log.exception("Model Lab candidate failed")
        error = "O provedor não concluiu a comparação."
    duration_ms = round((time.perf_counter() - started) * 1_000, 2)
    text = "".join(chunks)
    if not text.strip() and error is None:
        error = "O provedor concluiu sem devolver conteúdo."
    input_tokens = model_profiles.estimate_tokens(prompt)
    output_tokens = model_profiles.estimate_tokens(text) if text else 0
    return {
        "id": candidate_id,
        "profile_id": profile_id,
        "model": profile.get("model"),
        "text": text,
        "error": error,
        "metrics": {
            "first_token_ms": first_token_ms,
            "first_token_measured": first_token_measured,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": _estimated_candidate_cost(
                profile,
                input_tokens,
                output_tokens,
            ),
        },
    }


@app.get("/model-lab/presets")
def model_lab_preset_list() -> dict[str, Any]:
    return {"ok": True, "presets": model_lab.list_presets()}


@app.post("/model-lab/presets")
def model_lab_preset_save(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        preset = model_lab.save_preset(
            preset_id=str(payload.get("id") or "") or None,
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            criteria=(
                payload.get("criteria")
                if isinstance(payload.get("criteria"), list)
                else []
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "preset": preset}


@app.post("/model-lab/compare")
async def model_lab_compare(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    prompt = str(payload.get("prompt") or "").strip()
    left_id = str(payload.get("left_profile_id") or "")
    right_id = str(payload.get("right_profile_id") or "")
    if not prompt or not left_id or not right_id:
        raise HTTPException(
            status_code=400,
            detail="Prompt e os dois perfis são obrigatórios.",
        )
    metadata = {
        key: payload.get(key)
        for key in ("project_id", "conversation_id", "branch_id")
        if payload.get(key)
    }
    try:
        prepared = await orchestrator._prepare_dispatch(
            prompt,
            f"model-lab-{uuid.uuid4()}",
            None,
            metadata,
        )
        left, right = await asyncio.gather(
            _model_lab_candidate(prepared, left_id, prompt, "left"),
            _model_lab_candidate(prepared, right_id, prompt, "right"),
        )
        run = model_lab.record_run(
            prompt=prompt,
            candidates=[left, right],
            preset_id=str(payload.get("preset_id") or "balanced-quality"),
            context=metadata,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Preset ou contexto não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": bool(run["valid"]),
        "valid": bool(run["valid"]),
        "status": run["status"],
        "run": run,
    }


@app.get("/model-lab/runs")
def model_lab_run_list(limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "runs": model_lab.list_runs(limit=limit)}


@app.get("/model-lab/runs/{run_id}")
def model_lab_run_get(run_id: str) -> dict[str, Any]:
    item = model_lab.get_run(run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Comparação não encontrada.")
    return {"ok": True, "run": item}


@app.post("/model-lab/runs/{run_id}/winner")
def model_lab_select_winner(
    run_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        run = model_lab.select_winner(
            run_id,
            str(payload.get("candidate_id") or ""),
            scores=(
                payload.get("candidate_scores")
                if isinstance(payload.get("candidate_scores"), dict)
                else payload.get("scores")
                if isinstance(payload.get("scores"), dict)
                else None
            ),
            notes=str(payload.get("notes") or ""),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Comparação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "run": run}


@app.post("/model-lab/runs/{run_id}/profile")
def model_lab_create_profile(
    run_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        profile_payload = model_lab.winner_profile_payload(
            run_id,
            name=str(payload.get("name") or "") or None,
        )
        profile = model_profiles.create_profile(profile_payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Comparação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "profile": profile}


@app.post("/workflows/from-operations")
def workflow_from_operations(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        item = workflows.create_from_operations(
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            operation_ids=(
                payload.get("operation_ids")
                if isinstance(payload.get("operation_ids"), list)
                else []
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "workflow": item}


@app.get("/workflows")
def workflow_list(enabled: bool | None = None, limit: int = 200) -> dict[str, Any]:
    return {
        "ok": True,
        "workflows": workflows.list_workflows(enabled=enabled, limit=limit),
    }


@app.post("/workflows")
def workflow_create(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        item = workflows.create_workflow(
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            steps=payload.get("steps") if isinstance(payload.get("steps"), list) else [],
            variables=(
                payload.get("variables")
                if isinstance(payload.get("variables"), list)
                else []
            ),
            enabled=payload.get("enabled", True) is not False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "workflow": item}


@app.get("/workflows/{workflow_id}/revisions")
def workflow_revision_list(workflow_id: str) -> dict[str, Any]:
    try:
        return {"ok": True, "revisions": workflows.list_revisions(workflow_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")


@app.post("/workflows/{workflow_id}/restore/{revision_id}")
def workflow_restore(workflow_id: str, revision_id: str) -> dict[str, Any]:
    try:
        item = workflows.restore_revision(workflow_id, revision_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow ou revisão não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "workflow": item}


@app.post("/workflows/{workflow_id}/simulate")
def workflow_simulate(
    workflow_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return workflows.preview(
            workflow_id,
            values=payload.get("values") if isinstance(payload.get("values"), dict) else {},
            project_id=str(payload.get("project_id") or "") or None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/workflows/{workflow_id}/run")
async def workflow_run(
    workflow_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        materialized = workflows.materialize(
            workflow_id,
            values=payload.get("values") if isinstance(payload.get("values"), dict) else {},
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    project_id = str(payload.get("project_id") or "") or None
    confirmed = bool(payload.get("confirmed", False))
    run_id = workflows.begin_run(
        materialized["workflow"],
        inputs=materialized["inputs"],
    )
    operation_ids: list[str] = []
    results: list[dict[str, Any]] = []
    final_state = "completed"
    for index, step in enumerate(materialized["steps"]):
        operation = await _execute_controlled(
            step["action"],
            confirmed=confirmed,
            request_id=f"workflow-{run_id}",
            force_approval=not confirmed,
            project_id=project_id,
        )
        operation_ids.append(operation["id"])
        results.append({
            "step_id": step["id"],
            "name": step["name"],
            "operation_id": operation["id"],
            "state": operation["state"],
            "error": operation.get("error"),
        })
        if operation["state"] == "awaiting_approval":
            final_state = "awaiting_approval"
            break
        if operation["state"] in {"failed", "cancelled"}:
            final_state = operation["state"]
            if not step["continue_on_error"]:
                break
        if index >= 29:
            break
    run = workflows.finish_run(
        run_id,
        state=final_state,
        result={"steps": results, "project_id": project_id},
        operation_ids=operation_ids,
    )
    return {
        "ok": final_state == "completed",
        "pending_confirmation": final_state == "awaiting_approval",
        "run": run,
        "steps": results,
    }


@app.get("/workflows/{workflow_id}/runs")
def workflow_runs(workflow_id: str, limit: int = 100) -> dict[str, Any]:
    try:
        return {"ok": True, "runs": workflows.list_runs(workflow_id, limit=limit)}
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")


@app.get("/workflows/{workflow_id}")
def workflow_get(workflow_id: str) -> dict[str, Any]:
    item = workflows.get_workflow(workflow_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    return {"ok": True, "workflow": item}


@app.patch("/workflows/{workflow_id}")
def workflow_update(
    workflow_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        item = workflows.update_workflow(workflow_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "workflow": item}


@app.delete("/workflows/{workflow_id}")
def workflow_delete(workflow_id: str) -> dict[str, Any]:
    if not workflows.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow não encontrado.")
    return {"ok": True, "deleted": workflow_id}


@app.get("/projects/{project_id}/index-status")
def project_index_status(project_id: str) -> dict[str, Any]:
    try:
        return project_library.index_status(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


@app.post("/projects/{project_id}/reindex")
def project_reindex(project_id: str) -> dict[str, Any]:
    try:
        return project_library.reindex_project(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


@app.get("/projects/{project_id}/duplicates")
def project_duplicates(project_id: str) -> dict[str, Any]:
    try:
        return project_library.find_duplicates(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


@app.get("/projects/{project_id}/versions")
def project_versions(project_id: str) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "versions": project_library.list_versions(project_id),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


@app.get("/projects/{project_id}/documents/{document_id}/versions")
def project_document_versions(
    project_id: str,
    document_id: str,
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "versions": project_library.list_versions(project_id, document_id),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")


@app.post("/projects/{project_id}/semantic-index")
def project_semantic_index(
    project_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return project_library.set_semantic_index(
            project_id,
            bool(payload.get("enabled", True)),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    except (ImportError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/user-backup/preview")
def user_backup_preview(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return user_backup.preview(
            payload.get("components")
            if isinstance(payload.get("components"), list)
            else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/user-backup/create")
def user_backup_create(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    preflight = system_health.check(purpose="backup")
    if not preflight["preflight_passed"]:
        raise HTTPException(
            status_code=409,
            detail="A verificação de saúde bloqueou o backup.",
        )
    try:
        result = user_backup.create(
            components=(
                payload.get("components")
                if isinstance(payload.get("components"), list)
                else None
            ),
            password=str(payload.get("password") or "") or None,
            app_version=APP_VERSION,
        )
    except (ImportError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**result, "preflight": preflight["summary"]}


@app.get("/user-backup")
def user_backup_list() -> dict[str, Any]:
    return {"ok": True, "backups": user_backup.list_backups()}


@app.post("/user-backup/validate")
def user_backup_validate(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return user_backup.validate(
            str(payload.get("filename") or ""),
            password=str(payload.get("password") or "") or None,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/user-backup/restore")
def user_backup_restore(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    preflight = system_health.check(purpose="restore")
    if not preflight["preflight_passed"]:
        raise HTTPException(
            status_code=409,
            detail="A verificação de saúde bloqueou a restauração.",
        )
    try:
        return user_backup.restore(
            str(payload.get("filename") or ""),
            password=str(payload.get("password") or "") or None,
            components=(
                payload.get("components")
                if isinstance(payload.get("components"), list)
                else None
            ),
            confirmed=bool(payload.get("confirmed", False)),
            current_version=APP_VERSION,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup não encontrado.")
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/system-health/check")
def system_health_check(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    return system_health.check(purpose=str(payload.get("purpose") or "manual"))


@app.get("/system-health/history")
def system_health_history(limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "history": system_health.history(limit=limit)}


@app.post("/system-health/repair")
def system_health_repair(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return system_health.repair(
            str(payload.get("repair_id") or ""),
            project_id=str(payload.get("project_id") or "") or None,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/simulations")
def simulation_list(limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "simulations": simulations.list_simulations(limit=limit)}


@app.post("/simulations")
def simulation_create(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        item = simulations.create(
            name=str(payload.get("name") or ""),
            steps=payload.get("steps") if isinstance(payload.get("steps"), list) else [],
            project_id=str(payload.get("project_id") or "") or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "simulation": item}


@app.get("/simulations/{simulation_id}")
def simulation_get(simulation_id: str) -> dict[str, Any]:
    item = simulations.get(simulation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Simulação não encontrada.")
    return {"ok": True, "simulation": item}


@app.post("/simulations/{simulation_id}/approve")
def simulation_approve(
    simulation_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        item = simulations.approve(
            simulation_id,
            state_hash=str(payload.get("state_hash") or ""),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Simulação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "simulation": item}


@app.post("/simulations/{simulation_id}/convert")
def simulation_convert(
    simulation_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        workflow = simulations.convert_to_workflow(
            simulation_id,
            workflow_name=str(payload.get("name") or "") or None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Simulação não encontrada.")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "workflow": workflow}


@app.get("/evaluations/cases")
def evaluation_case_list(enabled: bool | None = None) -> dict[str, Any]:
    return {"ok": True, "cases": evaluations.list_cases(enabled=enabled)}


@app.post("/evaluations/cases")
def evaluation_case_save(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return {"ok": True, "case": evaluations.save_case(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/evaluations/presets")
def evaluation_preset_list() -> dict[str, Any]:
    return {"ok": True, "presets": evaluations.list_presets()}


@app.post("/evaluations/presets")
def evaluation_preset_save(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return {"ok": True, "preset": evaluations.save_preset(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/evaluations/run")
def evaluation_run(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "run": evaluations.run(
                outputs=(
                    payload.get("outputs")
                    if isinstance(payload.get("outputs"), dict)
                    else {}
                ),
                subject_type=str(payload.get("subject_type") or "profile"),
                subject_id=str(payload.get("subject_id") or "") or None,
                preset_id=str(payload.get("preset_id") or "essential-quality"),
                metrics=(
                    payload.get("metrics")
                    if isinstance(payload.get("metrics"), dict)
                    else {}
                ),
            ),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Preset não encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/evaluations/runs")
def evaluation_run_list(limit: int = 100) -> dict[str, Any]:
    return {"ok": True, "runs": evaluations.list_runs(limit=limit)}


@app.post("/evaluations/release-gate")
def evaluation_release_gate(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    return {
        "ok": True,
        "gate": evaluations.release_gate(
            payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            (
                payload.get("thresholds")
                if isinstance(payload.get("thresholds"), dict)
                else {}
            ),
            baseline=(
                payload.get("baseline")
                if isinstance(payload.get("baseline"), dict)
                else None
            ),
        ),
    }


@app.get("/agents/governance")
def agent_governance_status() -> dict[str, Any]:
    statuses = agent_governance.list_statuses()
    return {
        "ok": True,
        "agents": statuses,
        "available": sum(item["status"] == "available" for item in statuses),
        "unavailable": sum(item["status"] != "available" for item in statuses),
        "admission_ready": sum(item["admission_eligible"] for item in statuses),
        "compliant": all(
            item["available"] or item["status"] == "unavailable"
            for item in statuses
        ),
        "criteria": [
            "função única",
            "contratos e permissões documentados",
            "avaliações reais",
            "estado indisponível explícito",
            "ganho mensurável",
            "visibilidade apenas quando funcional",
        ],
    }


@app.post("/agents/candidates/validate")
def agent_candidate_validate(
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    return {"ok": True, "validation": agent_governance.gate_manifest(payload)}


# --------------------------------------------------------------------------- #
# WebSocket — live HUD telemetry
# --------------------------------------------------------------------------- #

@app.websocket("/ws/hud")
async def ws_hud(ws: WebSocket) -> None:
    """Stream periodic system snapshots to the HUD.

    Protocol:
      server -> client: { "type": "snapshot", "payload": {...} }
    """
    origin = ws.headers.get("origin")
    provided_token = (
        ws.headers.get("x-aether-token")
        or ws.query_params.get("token", "")
    )
    if settings.api_token and not hmac.compare_digest(
        provided_token,
        settings.api_token,
    ):
        await ws.close(code=1008, reason="Acesso local não autorizado.")
        return

    # Browsers must originate from the known local development UI. Packaged
    # Electron can report a file/null origin, but only while the per-launch
    # token above is active. Native clients commonly omit Origin altogether.
    packaged_origins = {"file://", "null"} if settings.api_token else set()
    allowed_origins = _LOCAL_UI_ORIGINS | packaged_origins
    if origin is not None and origin not in allowed_origins:
        await ws.close(code=1008, reason="Origem não autorizada.")
        return

    await ws.accept()
    try:
        while True:
            snap = await os_control.system_snapshot()
            await ws.send_json({"type": "snapshot", "payload": snap})
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("HUD WS closed: %s", exc)
