"""Agent package — domain-specialised assistants routed by the orchestrator.

Each agent receives the same message + shared context and returns a
:class:`AgentResult`. The orchestrator picks a winner (or fuses the top
results) before replying to the user.
"""
from .base import Agent, AgentContext, AgentResult
from .registry import build_default_agents, AGENT_REGISTRY

__all__ = ["Agent", "AgentContext", "AgentResult", "build_default_agents", "AGENT_REGISTRY"]
