"""Manifest and admission gate for Aether's existing agent registry.

This module does not create agents.  It documents the current set, prevents
placeholder specialists from competing for requests, and offers a pure
validation function for future candidates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_FUNCTIONAL_AGENTS = {
    "conversation",
    "logs",
    "automation",
    "files",
    "research",
    "programming",
    "designer",
    "agenda",
    "communication",
    "navigation",
    "system",
    "security",
    "vision",
}
_PLACEHOLDER_REASONS = {
    "marketing": "O agente ainda não possui fluxo verificável além de uma resposta genérica.",
    "seo": "O agente ainda não possui analisador ou contrato de evidências implementado.",
    "content": "A função já é coberta pelo modelo de conversa e não possui ganho medido próprio.",
    "commercial": "O agente não possui integração, avaliação ou saída operacional específica.",
    "financial": "O agente não possui fontes financeiras verificadas nem avaliação de precisão.",
    "database": "O agente não possui conector de banco autorizado nem contrato de consulta.",
    "memory": "A gestão de memória existe como sistema visual/API, não como agente funcional.",
}

_ROLES = {
    "conversation": "Diálogo geral e síntese final",
    "logs": "Telemetria local redigida",
    "automation": "Controle explícito de aplicativos e desktop",
    "files": "Operações e inspeção de arquivos",
    "research": "Pesquisa pública com abertura de fontes",
    "programming": "Inspeção de workspace e Git",
    "designer": "Orientação de interface e experiência",
    "marketing": "Estratégia de marketing",
    "seo": "Análise de SEO",
    "content": "Produção de conteúdo",
    "commercial": "Operações comerciais",
    "financial": "Finanças e mercados",
    "agenda": "Data, clima e calendário",
    "communication": "Leitura e pesquisa de e-mail",
    "navigation": "Abertura de destinos web conhecidos",
    "system": "Inspeção e ações do sistema",
    "security": "Criptografia e explicação de riscos",
    "database": "Acesso a bancos",
    "memory": "Gestão de memória",
    "vision": "Captura e análise visual",
}


def _default_manifest(agent_id: str) -> dict[str, Any]:
    available = agent_id in _FUNCTIONAL_AGENTS
    reason = _PLACEHOLDER_REASONS.get(agent_id)
    return {
        "agent_id": agent_id,
        "role": _ROLES[agent_id],
        "unique_function": available,
        "input_contract": {
            "type": "AgentContext",
            "required": ["user_message", "session_id"],
            "bounded": True,
        },
        "output_contract": {
            "type": "AgentResult",
            "required": [
                "agent_id",
                "agent_name",
                "reply",
                "confidence",
                "action",
                "status",
            ],
            "structured_action_only": True,
        },
        "permissions": (
            ["action-specific-policy", "global-safety-mode"]
            if agent_id not in {"conversation", "logs", "designer"}
            else ["read-local-context"]
        ),
        "errors": {
            "unavailable_state": "unavailable",
            "must_not_return_generic_success": True,
        },
        "dependencies": [],
        "evaluation": {
            "real_requests": 0,
            "passed": False,
            "quality_or_speed_gain_measured": False,
            "cases": [],
            "status": (
                "formal_evaluation_pending"
                if available
                else "not_evaluated"
            ),
        },
        "availability": {
            "status": "available" if available else "unavailable",
            "reason": reason,
            "visible_when_functional": available,
        },
    }


_MANIFESTS = {
    agent_id: _default_manifest(agent_id)
    for agent_id in _ROLES
}


def get_manifest(agent_id: str) -> dict[str, Any] | None:
    manifest = _MANIFESTS.get(str(agent_id or "").strip())
    return deepcopy(manifest) if manifest else None


def gate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a prospective manifest without registering an agent."""
    item = dict(manifest or {})
    failures: list[str] = []
    agent_id = str(item.get("agent_id") or "").strip()
    if not agent_id:
        failures.append("agent_id ausente")
    if not str(item.get("role") or "").strip():
        failures.append("função ausente")
    if not bool(item.get("unique_function")):
        failures.append("função não demonstrada como única")
    for contract in ("input_contract", "output_contract"):
        value = item.get(contract)
        if not isinstance(value, dict) or not value.get("required"):
            failures.append(f"{contract} incompleto")
    permissions = item.get("permissions")
    if not isinstance(permissions, list) or not permissions:
        failures.append("permissões não documentadas")
    errors = item.get("errors")
    if (
        not isinstance(errors, dict)
        or errors.get("unavailable_state") != "unavailable"
    ):
        failures.append("contrato de indisponibilidade ausente")
    evaluation = item.get("evaluation")
    if not isinstance(evaluation, dict):
        failures.append("avaliação ausente")
    else:
        if int(evaluation.get("real_requests") or 0) < 1:
            failures.append("nenhuma solicitação real de avaliação")
        cases = evaluation.get("cases")
        if (
            not isinstance(cases, list)
            or len(cases) < 3
            or any(
                not isinstance(case, dict) or not case.get("passed")
                for case in cases
            )
        ):
            failures.append("conjunto de avaliações reais incompleto")
        if not evaluation.get("passed"):
            failures.append("avaliações não aprovadas")
        if not evaluation.get("quality_or_speed_gain_measured"):
            failures.append("ganho mensurável não demonstrado")
    dependencies = item.get("dependencies")
    if not isinstance(dependencies, list):
        failures.append("dependências não documentadas")
    else:
        unavailable = [
            str(dependency.get("id") or "dependência")
            for dependency in dependencies
            if isinstance(dependency, dict)
            and dependency.get("available") is False
        ]
        if unavailable:
            failures.append(
                "dependências indisponíveis: " + ", ".join(unavailable)
            )
    return {
        "agent_id": agent_id or None,
        "eligible": not failures,
        "failures": failures,
        "checked_criteria": [
            "unique_function",
            "input_output_permissions_errors",
            "real_evaluations",
            "unavailable_state",
            "measurable_gain",
            "functional_visibility",
        ],
        "registered": agent_id in _MANIFESTS,
        "side_effects": False,
    }


def status(agent_id: str) -> dict[str, Any]:
    manifest = get_manifest(agent_id)
    if manifest is None:
        return {
            "agent_id": str(agent_id or ""),
            "status": "unavailable",
            "reason": "Agente não registrado.",
            "eligible": False,
        }
    gate = gate_manifest(manifest)
    declared = manifest["availability"]
    # Existing functional agents remain routable, but are not retroactively
    # presented as having completed measurements that do not exist. The full
    # admission gate applies to every future candidate.
    available = declared["status"] == "available"
    evaluation = manifest.get("evaluation") or {}
    return {
        "id": manifest["agent_id"],
        "agent_id": manifest["agent_id"],
        "name": manifest["role"],
        "role": manifest["role"],
        "status": "available" if available else "unavailable",
        "available": available,
        "reason": None if available else (
            declared.get("reason")
            or "; ".join(gate["failures"])
            or "Contrato de governança incompleto."
        ),
        "eligible": bool(gate["eligible"]),
        "admission_eligible": bool(gate["eligible"]),
        "permission_contract": ", ".join(manifest.get("permissions") or []),
        "evaluation_status": (
            "Avaliação formal concluída"
            if evaluation.get("passed")
            else "Avaliação formal pendente"
        ),
        "manifest": manifest,
    }


def list_statuses() -> list[dict[str, Any]]:
    return [status(agent_id) for agent_id in _MANIFESTS]


def routing_allowed(agent_id: str) -> bool:
    return bool(status(agent_id)["available"])
