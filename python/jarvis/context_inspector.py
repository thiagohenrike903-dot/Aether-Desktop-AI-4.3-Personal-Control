"""Redacted, metadata-only visibility into the context sent to a model."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import model_profiles, operations, privacy_control
from .redaction import redact_text

_MODEL_HISTORY_LIMIT = 8
_ATTACHMENT_LIMIT = 5
_ATTACHMENT_ITEM_CHARS = 50_000
_ATTACHMENT_TOTAL_CHARS = 120_000


def sanitize_action_for_model(
    action: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Reduce an executable action to a non-sensitive model summary.

    The full payload remains in the executor's in-memory operation cache. A
    language model only needs the operation category to explain what is about
    to happen; it does not need credentials, form values, message bodies,
    recipients, paths or signed URLs.
    """
    if not isinstance(action, dict):
        return None
    kind = str(action.get("type") or "").strip().lower()[:120]
    if not kind:
        return None
    affected = operations.affected_resources(action)
    summary: dict[str, Any] = {
        "type": kind,
        "affected_types": sorted({
            str(item.get("type") or "target")[:80]
            for item in affected
            if isinstance(item, dict)
        }),
        "affected_count": len(affected),
        "sanitized_for_model": True,
    }
    # These bounded scalar fields describe behavior without identifying the
    # user's resources or carrying free-form content.
    for key in (
        "operation",
        "dry_run",
        "by_type",
        "by_date",
        "days_old",
        "max",
        "headless",
        "overwrite",
    ):
        value = action.get(key)
        if isinstance(value, bool) or isinstance(value, (int, float)):
            summary[key] = value
        elif isinstance(value, str) and key == "operation":
            summary[key] = redact_text(value)[:80]
    return summary


def _profile_chain(profile_id: str | None) -> list[dict[str, Any]]:
    profile = (
        model_profiles.get_profile(profile_id)
        if profile_id
        else model_profiles.get_active_profile()
    )
    if profile is None:
        return []
    profiles = [profile]
    fallback_id = profile.get("fallback_profile_id")
    if fallback_id:
        fallback = model_profiles.get_profile(str(fallback_id))
        if fallback and fallback["id"] != profile["id"]:
            profiles.append(fallback)
    return profiles


def _provider_map(
    profile_id: str | None,
    conversation_id: str | None,
) -> dict[str, Any]:
    profiles = _profile_chain(profile_id)
    candidates: list[dict[str, Any]] = []
    for profile in profiles:
        destination = privacy_control.profile_destination(profile)
        decision = privacy_control.network_decision(
            str(destination.get("endpoint") or ""),
            provider=str(destination.get("provider") or "unconfigured"),
            conversation_id=conversation_id,
        )
        candidates.append({
            "profile_id": profile.get("id"),
            "provider": destination["provider"],
            "model": str(profile.get("model") or "")[:240],
            "endpoint": destination["endpoint"],
            "domain": destination["domain"],
            "destination": destination["destination"],
            "local": destination["local"],
            "endpoint_valid": destination["valid"],
            "allowed_by_privacy_mode": decision["allowed"],
            "blocked_by_privacy_mode": decision["blocked"],
            "available": bool(profile.get("available")),
        })
    return {
        "requested_profile_id": profile_id or (
            profiles[0].get("id") if profiles else None
        ),
        "candidates": candidates,
        "external_possible": any(
            item["destination"] == "external" for item in candidates
        ),
        "external_allowed": any(
            item["destination"] == "external"
            and item["allowed_by_privacy_mode"]
            for item in candidates
        ),
        "privacy_mode": privacy_control.effective_mode(conversation_id),
        "configured": bool(candidates),
    }


def _attachment_manifest(
    attachments: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    output: list[dict[str, Any]] = []
    remaining = _ATTACHMENT_TOTAL_CHARS
    total_content_chars = 0
    supplied = attachments if isinstance(attachments, list) else []
    for item in supplied[:_ATTACHMENT_LIMIT]:
        if not isinstance(item, dict):
            continue
        raw_content = str(item.get("content") or "")
        included_chars = min(
            len(raw_content),
            _ATTACHMENT_ITEM_CHARS,
            max(0, remaining),
        )
        remaining -= included_chars
        total_content_chars += included_chars
        try:
            size = max(0, int(item.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        output.append({
            "name": Path(str(item.get("name") or "arquivo")).name[:240],
            "mime_type": str(
                item.get("mime_type")
                or item.get("type")
                or "application/octet-stream"
            )[:120],
            "kind": str(item.get("kind") or "binary")[:40],
            "size": size,
            "content_available": bool(raw_content),
            "included_content_chars": included_chars,
            "truncated": included_chars < len(raw_content),
            "selection_reason": "Anexo fornecido nesta solicitação.",
        })
    return output, total_content_chars, {
        "supplied": len(supplied),
        "included": len(output),
        "item_limit": _ATTACHMENT_LIMIT,
        "total_content_char_limit": _ATTACHMENT_TOTAL_CHARS,
        "truncated": len(supplied) > len(output)
        or any(item["truncated"] for item in output),
    }


def build_manifest(
    *,
    user_message: str,
    history: list[dict[str, Any]],
    history_source: str,
    active_memories: list[dict[str, Any]],
    active_skills: list[dict[str, Any]],
    document_search: dict[str, Any],
    attachments: list[dict[str, Any]] | None,
    project_id: str | None,
    project_instructions: str = "",
    skill_knowledge: list[dict[str, str]] | None = None,
    model_profile_id: str | None = None,
    conversation_id: str | None = None,
    action: dict[str, Any] | None = None,
    draft: str = "",
    task_context: dict[str, Any] | None = None,
    context_omissions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a bounded manifest without copying private context contents."""
    model_history = history[-_MODEL_HISTORY_LIMIT:]
    message_items = [
        {
            "id": str(item.get("id") or "")[:160] or None,
            "role": str(item.get("role") or "unknown")[:40],
            "chars": len(str(item.get("content") or item.get("text") or "")),
            "used_by_model": item in model_history,
            "truncated": bool(item.get("context_truncated")),
            "selection_reason": "Histórico recente da ramificação ativa.",
        }
        for item in history
    ]
    memory_items = [
        {
            "id": str(item.get("id") or "")[:240],
            "scope": str(item.get("scope") or "")[:40],
            "project_id": item.get("project_id"),
            "kind": str(item.get("kind") or "")[:80],
            "key": redact_text(item.get("key") or "")[:240],
            "chars": len(str(item.get("value") or "")),
            "selection_reason": "Memória ativa compatível com o escopo atual.",
        }
        for item in active_memories[:60]
    ]
    skill_items = [
        {
            "id": str(item.get("id") or "")[:160],
            "name": redact_text(item.get("name") or "")[:240],
            "version": item.get("version"),
            "priority": item.get("priority"),
            "selection_reason": "Skill ativada por correspondência com a solicitação.",
        }
        for item in active_skills[:6]
    ]
    document_items: list[dict[str, Any]] = []
    for result in (document_search.get("results") or [])[:6]:
        if not isinstance(result, dict):
            continue
        citation = result.get("citation") if isinstance(result.get("citation"), dict) else {}
        document_items.append({
            "document_id": str(result.get("document_id") or "")[:160],
            "name": redact_text(result.get("name") or "")[:240],
            "excerpt_chars": len(str(result.get("excerpt") or "")),
            "citation": operations.safe_payload(citation),
            "selection_reason": "Trecho recuperado pela busca no projeto.",
        })
    attachment_items, attachment_content_chars, attachment_limits = (
        _attachment_manifest(attachments)
    )
    knowledge = skill_knowledge or []
    actual_history_chars = sum(
        len(str(item.get("content") or item.get("text") or ""))
        for item in model_history
    )
    memory_chars = sum(min(item["chars"], 2_500) for item in memory_items)
    document_chars = sum(item["excerpt_chars"] for item in document_items)
    knowledge_chars = sum(
        min(len(str(item.get("content") or "")), 20_000)
        for item in knowledge[:8]
    )
    estimated_text = "\n".join([
        str(user_message or ""),
        *(str(item.get("content") or item.get("text") or "") for item in model_history),
        str(draft or ""),
        "x" * memory_chars,
        "x" * document_chars,
        "x" * attachment_content_chars,
        "x" * knowledge_chars,
        str(project_instructions or "")[:12_000],
        (
            "x" * min(
                len(json.dumps(task_context, ensure_ascii=False, default=str)),
                20_000,
            )
            if task_context
            else ""
        ),
        json.dumps(sanitize_action_for_model(action), ensure_ascii=False),
    ])
    provider_map = _provider_map(model_profile_id, conversation_id)
    outbound_categories = [
        "current_message",
        *(["conversation_messages"] if model_history else []),
        *(["active_memories"] if memory_items else []),
        *(["project_documents"] if document_items else []),
        *(["attachments"] if attachment_items else []),
        *(["skill_knowledge"] if knowledge else []),
        *(["project_instructions"] if project_instructions else []),
        *(["task_context"] if task_context else []),
        *(["agent_draft"] if draft else []),
        *(["sanitized_action_summary"] if action else []),
    ]
    omissions = [
        {
            "category": str(item.get("category") or "unknown")[:80],
            "id": str(item.get("id") or "")[:240] or None,
            "reason": redact_text(
                item.get("reason") or "Removido pelo usuário antes da geração."
            )[:500],
        }
        for item in (context_omissions or [])[:500]
        if isinstance(item, dict)
    ]
    return {
        "version": 2,
        "conversation_id": conversation_id,
        "project_id": project_id,
        "history_source": history_source,
        "messages": message_items,
        "memories": memory_items,
        "skills": skill_items,
        "documents": document_items,
        "attachments": attachment_items,
        "instructions": {
            "project": bool(project_instructions),
            "project_chars": min(len(project_instructions), 12_000),
            "skill_knowledge_files": len(knowledge[:8]),
            "selection_reason": (
                "Instruções do projeto ativo."
                if project_instructions
                else None
            ),
        },
        "task_context": {
            "included": bool(task_context),
            "chars": len(json.dumps(task_context, ensure_ascii=False, default=str))
            if task_context
            else 0,
            "selection_reason": (
                "Contexto da tarefa ativa."
                if task_context
                else None
            ),
        },
        "agent_draft": {
            "included": bool(draft),
            "chars": len(str(draft or "")),
            "selection_reason": (
                "Rascunho produzido pelo agente selecionado."
                if draft
                else None
            ),
        },
        "omissions": omissions,
        "action": sanitize_action_for_model(action),
        "estimate": {
            "input_tokens": model_profiles.estimate_tokens(estimated_text),
            "source": "local_estimate",
            "includes_generated_draft": bool(draft),
            "model_history_chars": actual_history_chars,
        },
        "limits": {
            "model_history_messages": _MODEL_HISTORY_LIMIT,
            "history_truncated_for_model": len(history) > len(model_history),
            "memory_limit_reached": len(active_memories) >= 60,
            "document_limit_reached": len(document_search.get("results") or []) >= 6,
            "attachments": attachment_limits,
            "excluded_by_user": len(omissions),
            "excluded_by_category": {
                category: sum(
                    item["category"] == category for item in omissions
                )
                for category in sorted({
                    item["category"] for item in omissions
                })
            },
        },
        "privacy": {
            **provider_map,
            "outbound_categories": outbound_categories,
            "full_values_in_manifest": False,
            "local_only": [
                "full_executable_action",
                "disabled_memories",
                "control_center_audit_payload",
            ],
            "note": (
                "As categorias listadas podem ser enviadas a um provedor externo "
                "quando external_possible=true; o manifesto contém apenas metadados."
            ),
        },
    }
