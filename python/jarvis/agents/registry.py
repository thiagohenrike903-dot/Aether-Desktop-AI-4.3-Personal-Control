"""Registry of the default Aether agents.

The names/roles are the ones listed in the spec; their *behaviour* ranges
from a simple keyword-driven short reply (for e.g. ``Logs``) to a Gemini
call (for ``Conversation``, ``Research``) and direct OS delegation (for
``Automation``, ``System``).
"""
from __future__ import annotations

from .base import Agent, AgentContext, AgentResult
from .specialists import build_specialist_agents


def build_default_agents() -> list[Agent]:
    """Return the complete default agent set used by the orchestrator."""

    async def conversation(ctx: AgentContext) -> AgentResult:
        reply = (
            f"Entendi sua solicitação: “{ctx.user_message}”. "
            "Posso ajudar a detalhar os próximos passos. Para respostas "
            "geradas por IA, configure um provedor de modelo no arquivo .env."
        )
        return AgentResult(
            agent_id="conversation",
            agent_name="Conversation",
            reply=reply,
            confidence=0.25,  # deliberately low so domain agents win when relevant
        )

    async def logs(ctx: AgentContext) -> AgentResult:
        return AgentResult(
            agent_id="logs",
            agent_name="Logs",
            reply="A atividade foi registrada no histórico técnico local.",
            confidence=0.5,
            side_effects=[{"type": "log", "message": ctx.user_message}],
        )

    # Specialists: each one is a small class that knows its own domain.
    specialists = build_specialist_agents()

    base: list[Agent] = [
        Agent(
            id="conversation",
            name="Conversation",
            role="General dialog and reasoning",
            keywords=["hello", "how are you", "what is", "explain", "quem", "como"],
            domains=["conversation", "general"],
            handler=conversation,
        ),
        Agent(
            id="logs",
            name="Logs",
            role="System log archival",
            keywords=["log", "logar", "registrar"],
            domains=["logs"],
            handler=logs,
        ),
    ]

    return base + specialists


# A handy lookup table — orchestrator can fetch a single agent by id without
# scanning the list.
AGENT_REGISTRY: dict[str, Agent] = {a.id: a for a in build_default_agents()}
