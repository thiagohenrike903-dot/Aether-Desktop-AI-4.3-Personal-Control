"""Central orchestrator.

Picks the best agent(s) for the user's request, gathers their results,
returns a fused answer plus a structured action for the executor to run.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import (
    agent_governance,
    context_inspector,
    conversations,
    llm,
    memory,
    project_library,
    skills,
    workspace,
)
from .agents import AGENT_REGISTRY, AgentContext, AgentResult
from .memory import add_turn, get_preferences, get_short_term_history

log = logging.getLogger("jarvis.orchestrator")

_PERSISTED_ACTION_FIELDS = {
    "type",
    "target",
    "operation",
    "source",
    "destination",
    "url",
    "selector",
    "query",
    "city",
    "dry_run",
    "days_old",
    "by_type",
    "by_date",
    "remote",
    "branch",
    "name",
    "summary",
    "start_time",
    "end_time",
    "plugin_action",
    "headless",
    "max",
}


def _memory_safe_action(action: dict[str, Any] | None) -> dict[str, Any] | None:
    """Retain an audit summary without persisting message/form/secret bodies."""
    if not isinstance(action, dict):
        return None
    safe: dict[str, Any] = {}
    for key in _PERSISTED_ACTION_FIELDS:
        value = action.get(key)
        if isinstance(value, bool) or value is None:
            if value is not None:
                safe[key] = value
        elif isinstance(value, (int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:1_000]
        elif isinstance(value, list):
            safe[key] = [
                item[:500] if isinstance(item, str) else item
                for item in value[:30]
                if isinstance(item, (str, int, float, bool))
            ]
    return safe or None


def _memory_safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep useful attachment metadata without persisting file contents."""
    source = dict(metadata or {})
    attachments = source.get("attachments")
    if isinstance(attachments, list):
        safe_attachments: list[dict[str, Any]] = []
        for item in attachments[:5]:
            if not isinstance(item, dict):
                continue
            try:
                size = max(0, int(item.get("size") or 0))
            except (TypeError, ValueError):
                size = 0
            safe_attachments.append({
                "name": str(item.get("name") or "arquivo")[:240],
                "mime_type": str(
                    item.get("mime_type")
                    or item.get("type")
                    or "application/octet-stream"
                )[:120],
                "kind": str(item.get("kind") or "binary")[:40],
                "size": size,
            })
        source["attachments"] = safe_attachments
    if isinstance(source.get("context_exclusions"), dict):
        normalized = _normalize_context_exclusions(source)
        source["context_exclusions"] = {
            category: sorted(identifiers)
            for category, identifiers in normalized["identifiers"].items()
            if identifiers
        }
    return source


_CONTEXT_EXCLUSION_CATEGORIES = {
    "messages",
    "memories",
    "skills",
    "documents",
    "attachments",
    "instructions",
}


def _normalize_context_exclusions(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Normalize user-selected context removals into bounded identifiers."""
    raw = metadata.get("context_exclusions")
    if not isinstance(raw, dict):
        raw = {}
    identifiers: dict[str, set[str]] = {
        category: set() for category in _CONTEXT_EXCLUSION_CATEGORIES
    }
    reasons: dict[tuple[str, str], str] = {}

    def add(category: str, identifier: object, reason: object = "") -> None:
        value = str(identifier or "").strip()[:240]
        if not value:
            return
        identifiers[category].add(value)
        if reason:
            reasons[(category, value)] = str(reason).strip()[:500]

    for category in _CONTEXT_EXCLUSION_CATEGORIES:
        value = raw.get(category)
        if value is True:
            add(category, "*")
        elif isinstance(value, str):
            add(category, value)
        elif isinstance(value, list):
            for item in value[:500]:
                if isinstance(item, dict):
                    add(
                        category,
                        item.get("id")
                        or item.get("name")
                        or item.get("key")
                        or ("*" if item.get("all") else ""),
                        item.get("reason"),
                    )
                else:
                    add(category, item)
        elif isinstance(value, dict):
            if value.get("all"):
                add(category, "*", value.get("reason"))
            elif value.get("id") or value.get("name") or value.get("key"):
                add(
                    category,
                    value.get("id") or value.get("name") or value.get("key"),
                    value.get("reason"),
                )
            else:
                for key, item_reason in list(value.items())[:500]:
                    add(category, key, item_reason)

    # Friendly aliases accepted from earlier UI experiments.
    if raw.get("project_instructions") is True:
        add("instructions", "*")
    return {"identifiers": identifiers, "reasons": reasons}


def _exclusion_match(
    exclusions: dict[str, Any],
    category: str,
    candidates: list[str],
) -> tuple[str, str] | None:
    configured = exclusions["identifiers"][category]
    matched = "*" if "*" in configured else next(
        (candidate for candidate in candidates if candidate in configured),
        "",
    )
    if not matched:
        return None
    reason = exclusions["reasons"].get(
        (category, matched),
        "Removido pelo usuário antes da geração.",
    )
    return matched, reason


def _history_for_request(
    session_id: str,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    conversation_id = str(metadata.get("conversation_id") or "").strip()
    if conversation_id and conversations.get(conversation_id) is not None:
        return (
            conversations.context_history(
                conversation_id,
                parent_message_id=str(
                    metadata.get("parent_message_id") or ""
                ).strip() or None,
                branch_id=str(metadata.get("branch_id") or "").strip() or None,
            ),
            "conversation",
        )
    if conversation_id:
        return [], "new_conversation"
    return get_short_term_history(session_id), "session"


async def _collect_context(
    user_message: str,
    session_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    source = dict(metadata or {})
    exclusions = _normalize_context_exclusions(source)
    omissions: list[dict[str, Any]] = []

    def omitted(
        category: str,
        identifier: str,
        reason: str,
    ) -> None:
        omissions.append({
            "category": category,
            "id": identifier,
            "reason": reason,
        })

    raw_history, history_source = _history_for_request(session_id, source)
    history: list[dict[str, Any]] = []
    for index, item in enumerate(raw_history):
        identifier = str(item.get("id") or f"index:{index}")
        match = _exclusion_match(
            exclusions,
            "messages",
            [identifier, f"index:{index}"],
        )
        if match:
            omitted("messages", identifier, match[1])
        else:
            history.append(item)
    project_root = str(source.get("project_root") or "") or None
    project_id = str(source.get("project_id") or "") or None
    matched_skills = skills.match_skills(user_message, project_root)
    active_skills: list[dict[str, Any]] = []
    for item in matched_skills:
        identifier = str(item.get("id") or "")
        match = _exclusion_match(exclusions, "skills", [identifier])
        if match:
            omitted("skills", identifier, match[1])
        else:
            active_skills.append(item)

    candidate_memories = memory.list_memories(
        scope="global",
        enabled=True,
        limit=40,
    )
    if project_id:
        candidate_memories.extend(
            memory.list_memories(
                scope="project",
                project_id=project_id,
                enabled=True,
                limit=40,
            )
        )
    elif project_root:
        candidate_memories.extend(
            memory.list_memories(
                scope="project",
                project_id=project_root,
                enabled=True,
                limit=40,
            )
        )
    active_memories: list[dict[str, Any]] = []
    for item in candidate_memories[:60]:
        identifier = str(item.get("id") or "")
        match = _exclusion_match(exclusions, "memories", [identifier])
        if match:
            omitted("memories", identifier, match[1])
        else:
            active_memories.append(item)

    document_search: dict[str, Any] = {
        "grounded": False,
        "results": [],
        "citations": [],
    }
    if project_id:
        try:
            document_search = project_library.search(
                project_id,
                user_message,
                limit=6,
            )
        except (KeyError, ValueError):
            document_search = {
                "grounded": False,
                "results": [],
                "citations": [],
            }
    filtered_results: list[dict[str, Any]] = []
    filtered_citations: list[dict[str, Any]] = []
    for result in document_search.get("results", []):
        citation = (
            result.get("citation")
            if isinstance(result.get("citation"), dict)
            else {}
        )
        document_id = str(result.get("document_id") or "")
        chunk = str(citation.get("chunk") if citation.get("chunk") is not None else "")
        compound = f"{document_id}:{chunk}" if chunk else document_id
        match = _exclusion_match(
            exclusions,
            "documents",
            [compound, document_id],
        )
        if match:
            omitted("documents", compound or document_id, match[1])
        else:
            filtered_results.append(result)
            filtered_citations.append(citation)
    document_search = {
        **document_search,
        "results": filtered_results,
        "citations": filtered_citations,
        "grounded": bool(filtered_results),
    }

    prompt_memory = [
        {
            "id": item["id"],
            "scope": item["scope"],
            "kind": item["kind"],
            "key": item["key"],
            "value": item["value"][:2_500],
        }
        for item in active_memories
    ]
    project_instructions = ""
    if project_id:
        project = project_library.get_project(project_id)
        project_instructions = (
            str(project.get("instructions") or "").strip()
            if project
            else ""
        )
        if project_instructions:
            instruction_id = f"project:{project_id}:instructions"
            match = _exclusion_match(
                exclusions,
                "instructions",
                [instruction_id, project_id, "project"],
            )
            if match:
                omitted("instructions", instruction_id, match[1])
                project_instructions = ""
            else:
                prompt_memory.append({
                    "id": instruction_id,
                    "scope": "project",
                    "kind": "instructions",
                    "key": "Instruções do projeto",
                    "value": project_instructions[:12_000],
                })
    prompt_memory.extend(
        {
            "id": f"document:{result['document_id']}:{result['citation']['chunk']}",
            "scope": "project_document",
            "kind": "source",
            "key": result["name"],
            "value": result["excerpt"],
            "citation": result["citation"],
        }
        for result in document_search.get("results", [])
    )

    skill_knowledge: list[dict[str, str]] = []
    if (
        project_root
        and workspace.get_root()
        and str(workspace.get_root()) == project_root
    ):
        knowledge_paths = list(dict.fromkeys(
            path
            for item in active_skills
            for path in item.get("knowledge_files", [])
        ))
        for path in knowledge_paths[:8]:
            result = await workspace.read_file(path)
            if result.get("ok"):
                skill_knowledge.append({
                    "path": result["path"],
                    "content": result["content"][:20_000],
                })
    supplied_attachments = (
        source.get("attachments")
        if isinstance(source.get("attachments"), list)
        else []
    )
    attachments: list[dict[str, Any]] = []
    for index, item in enumerate(supplied_attachments):
        if not isinstance(item, dict):
            continue
        identifier = str(
            item.get("id")
            or item.get("name")
            or f"index:{index}"
        )
        candidates = [
            identifier,
            str(item.get("name") or ""),
            f"index:{index}",
        ]
        match = _exclusion_match(exclusions, "attachments", candidates)
        if match:
            omitted("attachments", identifier, match[1])
        else:
            attachments.append(item)
    return {
        "history": history,
        "history_source": history_source,
        "project_root": project_root,
        "project_id": project_id,
        "project_instructions": project_instructions,
        "active_skills": active_skills,
        "active_memories": active_memories,
        "document_search": document_search,
        "prompt_memory": prompt_memory,
        "skill_knowledge": skill_knowledge,
        "attachments": attachments,
        "model_profile_id": str(source.get("model_profile_id") or "") or None,
        "conversation_id": str(source.get("conversation_id") or "") or None,
        "request_id": str(source.get("request_id") or "") or None,
        "task_context": (
            source.get("active_task")
            if isinstance(source.get("active_task"), dict)
            else None
        ),
        "context_omissions": omissions,
    }


async def preview_context(
    user_message: str,
    *,
    session_id: str = "preview",
    metadata: dict[str, Any] | None = None,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect context locally without routing agents or calling a model."""
    collected = await _collect_context(user_message, session_id, metadata)
    return context_inspector.build_manifest(
        user_message=user_message,
        history=collected["history"],
        history_source=collected["history_source"],
        active_memories=collected["active_memories"],
        active_skills=collected["active_skills"],
        document_search=collected["document_search"],
        attachments=collected["attachments"],
        project_id=collected["project_id"],
        project_instructions=collected["project_instructions"],
        skill_knowledge=collected["skill_knowledge"],
        model_profile_id=collected["model_profile_id"],
        conversation_id=collected["conversation_id"],
        action=action,
        task_context=collected["task_context"],
        context_omissions=collected["context_omissions"],
    )


async def _prepare_dispatch(
    user_message: str,
    session_id: str,
    intent_hint: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    collected = await _collect_context(user_message, session_id, metadata)
    agent_metadata = dict(metadata or {})
    agent_metadata["attachments"] = collected["attachments"]
    ctx = AgentContext(
        user_message=user_message,
        intent_hint=intent_hint,
        session_id=session_id,
        history=collected["history"],
        preferences=get_preferences(),
        metadata=agent_metadata,
    )

    # 1. Score every agent, in parallel.
    # Logs is telemetry-only. Letting it compete for the answer made generic
    # conversation resolve to a technical logging acknowledgement.
    candidates = [
        a
        for a in AGENT_REGISTRY.values()
        if (
            a.handler is not None
            and a.id != "logs"
            and agent_governance.routing_allowed(a.id)
        )
    ]
    scored = [(a, a.score(ctx)) for a in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    top = [a for a, s in scored[:3] if s > 0]
    if not top:
        top = [AGENT_REGISTRY["conversation"]]
    # Always run the Logs agent in the background for telemetry, but don't include
    # its result in the fused response.
    bg = [AGENT_REGISTRY["logs"]]

    async def _run(a) -> AgentResult:
        return await a.run(ctx)

    results: list[AgentResult] = await asyncio.gather(*[_run(a) for a in top + bg])
    top_results = results[: len(top)]
    bg_results = results[len(top):]

    # 2. Pick a winner: highest confidence with a real reply.
    #    If a non-Conversation agent has a structured action, prefer it.
    def _rank(r: AgentResult) -> tuple[int, float]:
        has_action = 1 if r.action else 0
        return (has_action, r.confidence)

    winner = max(top_results, key=_rank)

    # 3. Build the final action — only emit one if the top result has one.
    final_action = winner.action
    if isinstance(final_action, dict):
        # Carry request scope into the control plane.  Without this, a project
        # safety policy would not apply to an action produced by an agent and
        # network flows could not be attributed to the active conversation.
        final_action = dict(final_action)
        if collected["project_id"]:
            final_action.setdefault("project_id", collected["project_id"])
        if collected["conversation_id"]:
            final_action.setdefault(
                "conversation_id",
                collected["conversation_id"],
            )
        if collected["request_id"]:
            final_action.setdefault("request_id", collected["request_id"])

    # 4. Convert the specialist's terse routing result into a real, natural
    # response. The model can only rewrite text; it cannot alter or execute the
    # structured action selected above.
    active_skills = collected["active_skills"]
    active_memories = collected["active_memories"]
    document_search = collected["document_search"]
    context_manifest = context_inspector.build_manifest(
        user_message=user_message,
        history=collected["history"],
        history_source=collected["history_source"],
        active_memories=active_memories,
        active_skills=active_skills,
        document_search=document_search,
        attachments=collected["attachments"],
        project_id=collected["project_id"],
        project_instructions=collected["project_instructions"],
        skill_knowledge=collected["skill_knowledge"],
        model_profile_id=collected["model_profile_id"],
        conversation_id=collected["conversation_id"],
        action=final_action,
        draft=winner.reply,
        task_context=collected["task_context"],
        context_omissions=collected["context_omissions"],
    )
    llm_context = {
        "user_message": user_message,
        "history": ctx.history,
        "draft": winner.reply,
        "action": final_action,
        "active_skills": active_skills,
        "task_context": collected["task_context"],
        "project_memory": collected["prompt_memory"],
        "skill_knowledge": collected["skill_knowledge"],
        "attachments": collected["attachments"],
        "model_profile_id": collected["model_profile_id"],
        "conversation_id": collected["conversation_id"],
        "request_id": collected["request_id"],
        "privacy_categories": list(
            context_manifest.get("privacy", {}).get("outbound_categories", [])
        ),
    }
    return {
        "ctx": ctx,
        "winner": winner,
        "top_results": top_results,
        "bg_results": bg_results,
        "final_action": final_action,
        "active_skills": active_skills,
        "active_memories": active_memories,
        "document_search": document_search,
        "context_manifest": context_manifest,
        "model": {},
        "llm_context": llm_context,
    }


def _payload(prepared: dict[str, Any]) -> dict[str, Any]:
    winner: AgentResult = prepared["winner"]
    top_results: list[AgentResult] = prepared["top_results"]
    bg_results: list[AgentResult] = prepared["bg_results"]
    model = prepared.get("model") or {}
    usage = model.get("usage") if isinstance(model, dict) else None
    response_metrics = (
        usage
        if isinstance(usage, dict) and usage.get("scope") == "response"
        else None
    )
    return {
        "reply": winner.reply,
        "action": prepared["final_action"],
        "agents": [
            {
                "id": result.agent_id,
                "name": result.agent_name,
                "confidence": result.confidence,
                "reply": result.reply,
                "status": result.status,
                "error": result.error,
            }
            for result in top_results
        ],
        "side_effects": [
            side_effect
            for result in bg_results
            for side_effect in result.side_effects
        ],
        "winner": winner.agent_id,
        "used_skills": [
            {"id": item["id"], "name": item["name"], "version": item["version"]}
            for item in prepared["active_skills"]
        ],
        "used_memories": [
            {
                "id": item["id"],
                "scope": item["scope"],
                "project_id": item.get("project_id"),
                "kind": item["kind"],
                "key": item["key"],
            }
            for item in prepared["active_memories"]
        ],
        "sources": prepared["document_search"].get("citations", []),
        "citations": prepared["document_search"].get("citations", []),
        "sources_retrieved": bool(prepared["document_search"].get("grounded")),
        "grounded": bool(
            prepared["document_search"].get("grounded")
            and model.get("used_profile_id")
        ),
        "context_manifest": prepared.get("context_manifest") or {},
        "model": model,
        "metrics": response_metrics,
    }


def _persist(
    prepared: dict[str, Any],
    user_message: str,
    session_id: str,
    metadata: dict[str, Any] | None,
) -> None:
    winner: AgentResult = prepared["winner"]
    add_turn("user", user_message, session_id, _memory_safe_metadata(metadata))
    add_turn(
        "assistant",
        winner.reply,
        session_id,
        metadata={
            "agent": winner.agent_id,
            "action": _memory_safe_action(prepared["final_action"]),
            "confidence": winner.confidence,
        },
    )


async def dispatch(
    user_message: str,
    session_id: str = "default",
    intent_hint: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the user message through the multi-agent stack."""
    prepared = await _prepare_dispatch(
        user_message,
        session_id,
        intent_hint,
        metadata,
    )
    winner: AgentResult = prepared["winner"]
    natural_reply = await llm.respond(
        **prepared["llm_context"],
    )
    if natural_reply:
        winner.reply = natural_reply
    prepared["model"] = llm.last_response_metadata()

    _persist(prepared, user_message, session_id, metadata)
    return _payload(prepared)


async def dispatch_stream(
    user_message: str,
    session_id: str = "default",
    intent_hint: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Yield routing stages and native model deltas.

    Buffered providers produce no ``token`` events; their completed response
    arrives in the final result with ``stream_mode=buffered``.
    """
    yield {
        "type": "status",
        "stage": "routing",
        "message": "Selecionando agentes e ferramentas.",
    }
    prepared = await _prepare_dispatch(
        user_message,
        session_id,
        intent_hint,
        metadata,
    )
    if prepared["final_action"]:
        yield {"type": "action", "action": prepared["final_action"]}
    yield {
        "type": "status",
        "stage": "thinking",
        "message": "Gerando a resposta.",
    }
    winner: AgentResult = prepared["winner"]
    stream_mode = "local"
    usage: dict[str, Any] | None = None
    fallback_used = False
    async for event in llm.stream_respond(**prepared["llm_context"]):
        event_type = event.get("type")
        if event_type == "token":
            stream_mode = "native"
            fallback_used = bool(event.get("fallback_used"))
            yield event
        elif event_type in {"buffered_result", "stream_end"}:
            if event.get("text"):
                winner.reply = str(event["text"])
            stream_mode = str(event.get("stream_mode") or stream_mode)
            usage = event.get("usage")
            fallback_used = bool(event.get("fallback_used"))
        elif event_type == "unavailable":
            stream_mode = "local"

    _persist(prepared, user_message, session_id, metadata)
    prepared["model"] = llm.last_response_metadata()
    yield {
        "type": "result",
        "payload": _payload(prepared),
        "stream_mode": stream_mode,
        "usage": usage,
        "fallback_used": fallback_used,
    }
