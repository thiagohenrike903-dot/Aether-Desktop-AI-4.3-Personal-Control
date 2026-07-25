"""Base classes for the multi-agent system.

An agent is just a function from ``(message, context) -> AgentResult`` with
some metadata so the orchestrator can route intelligently.  We keep this
deliberately small — heavy lifting (Gemini calls, OS actions) lives in the
*specific* agent modules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


def _keyword_matches(message: str, keyword: str) -> bool:
    phrase = re.escape(keyword).replace(r"\ ", r"\s+")
    return re.search(
        rf"(?<!\w){phrase}(?!\w)",
        message,
        flags=re.IGNORECASE,
    ) is not None


@dataclass
class AgentContext:
    """Shared state passed to every agent on every call.

    Fields:
      user_message: the raw text the user just said/typed
      intent_hint: optional override from the orchestrator's classifier
      history: short-term memory turns (list of dicts)
      facts: long-term facts the user has explicitly set
      preferences: user preferences
      session_id: a stable id for the current session (frontend generated)
      metadata: free-form per-request bag (locale, command mode, etc.)
    """

    user_message: str
    intent_hint: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    preferences: dict[str, str] = field(default_factory=dict)
    session_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """A single agent's response."""

    agent_id: str
    agent_name: str
    reply: str
    confidence: float = 1.0
    action: dict[str, Any] | None = None  # structured command for the executor
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    status: str = "available"


class Agent:
    def __init__(
        self,
        id: str,
        name: str,
        role: str,
        keywords: list[str] | None = None,
        domains: list[str] | None = None,
        handler: Callable[[AgentContext], Awaitable[AgentResult]] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.role = role
        self.keywords = [k.lower() for k in (keywords or [])]
        self.domains = [d.lower() for d in (domains or [])]
        self.handler = handler

    def score(self, ctx: AgentContext) -> float:
        """Return 0..1 affinity for the current request.

        The scoring strategy:
          - exact domain hint match  -> 0.95
          - any keyword hit (loose substring) -> 0.3 per hit, capped at 0.9
          - no hit -> 0, allowing the Conversation agent to be the fallback
        """
        msg = ctx.user_message.lower()
        if not self.keywords and not self.domains:
            return 0.0
        if ctx.intent_hint and ctx.intent_hint.lower() in self.domains:
            return 0.95
        hits = sum(1 for keyword in self.keywords if _keyword_matches(msg, keyword))
        return min(0.9, hits * 0.3) if hits else 0.0

    async def run(self, ctx: AgentContext) -> AgentResult:
        # Lazy import avoids coupling the lightweight agent dataclasses to the
        # registry at module-import time.
        from .. import agent_governance

        governance = agent_governance.status(self.id)
        if governance["status"] != "available":
            reason = str(governance.get("reason") or "Função indisponível.")
            return AgentResult(
                agent_id=self.id,
                agent_name=self.name,
                reply=f"Agente indisponível: {reason}",
                confidence=0.0,
                error=reason,
                status="unavailable",
            )
        if self.handler is None:
            return AgentResult(
                agent_id=self.id,
                agent_name=self.name,
                reply="Agente indisponível: nenhum handler funcional registrado.",
                confidence=0.0,
                error="Nenhum handler funcional registrado.",
                status="unavailable",
            )
        try:
            return await self.handler(ctx)
        except Exception as exc:  # pragma: no cover
            return AgentResult(
                agent_id=self.id,
                agent_name=self.name,
                reply=f"Agent '{self.name}' encountered an error.",
                confidence=0.0,
                error=str(exc),
                status="error",
            )
