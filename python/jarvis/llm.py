"""LLM client — thin wrapper around the multi-provider system.

Keeps backward compatibility with existing imports while routing
to the new provider-agnostic interface.
"""
from __future__ import annotations

import contextvars
import time
from collections.abc import AsyncIterator
from typing import Any

from .llm_providers import (
    respond as _respond,
    stream_respond as _stream_respond,
    analyze_image as _analyze_image,
    get_provider,
)
from . import model_profiles

_LAST_RESPONSE_METADATA: contextvars.ContextVar[dict[str, Any]] = (
    contextvars.ContextVar("aether_last_response_metadata", default={})
)


def _input_text(
    user_message: str,
    history: list[dict[str, Any]],
    draft: str,
) -> str:
    return "\n".join(
        [
            *(str(turn.get("content") or "") for turn in history[-8:]),
            user_message,
            draft,
        ]
    )


def _profile_chain(requested_profile_id: str | None = None) -> list[dict[str, Any]]:
    requested = (
        model_profiles.get_profile(requested_profile_id)
        if requested_profile_id
        else model_profiles.get_active_profile()
    )
    if requested is None:
        return []
    profiles = [requested]
    fallback_id = requested.get("fallback_profile_id")
    if fallback_id:
        fallback = model_profiles.get_profile(str(fallback_id))
        if fallback and fallback["id"] != requested["id"]:
            profiles.append(fallback)
    return profiles


def last_response_metadata() -> dict[str, Any]:
    return dict(_LAST_RESPONSE_METADATA.get())


async def respond(
    user_message: str,
    history: list[dict[str, Any]],
    draft: str,
    action: dict[str, Any] | None,
    active_skills: list[dict[str, Any]] | None = None,
    task_context: dict[str, Any] | None = None,
    project_memory: list[dict[str, Any]] | None = None,
    skill_knowledge: list[dict[str, str]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    model_profile_id: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    privacy_categories: list[str] | None = None,
) -> str | None:
    input_tokens = model_profiles.estimate_tokens(
        _input_text(user_message, history, draft)
    )
    profiles = _profile_chain(model_profile_id)
    requested_profile_id = profiles[0]["id"] if profiles else model_profile_id
    started = time.perf_counter()
    privacy_kwargs = (
        {
            "conversation_id": conversation_id,
            "request_id": request_id,
            "privacy_categories": privacy_categories,
        }
        if conversation_id or request_id or privacy_categories
        else {}
    )
    for index, profile in enumerate(profiles):
        if not profile.get("enabled") or not profile.get("model"):
            continue
        if model_profiles.limit_reached(profile):
            continue
        response = await _respond(
            user_message,
            history,
            draft,
            action,
            active_skills,
            task_context,
            project_memory,
            skill_knowledge,
            attachments,
            profile,
            **privacy_kwargs,
        )
        output_tokens = model_profiles.estimate_tokens(response or "")
        duration_ms = round((time.perf_counter() - started) * 1_000, 2)
        model_profiles.record_usage(
            profile,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failed=response is None,
        )
        if response:
            _LAST_RESPONSE_METADATA.set({
                "requested_profile_id": requested_profile_id,
                "used_profile_id": profile["id"],
                "fallback_used": index > 0,
                "latency_ms": duration_ms,
                "stream_mode": "buffered",
                "usage": model_profiles.response_usage(
                    profile,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                ),
            })
            return response
    _LAST_RESPONSE_METADATA.set({
        "requested_profile_id": requested_profile_id,
        "used_profile_id": None,
        "fallback_used": False,
        "latency_ms": round((time.perf_counter() - started) * 1_000, 2),
        "stream_mode": "unavailable",
        "usage": None,
    })
    return None


async def stream_respond(
    user_message: str,
    history: list[dict[str, Any]],
    draft: str,
    action: dict[str, Any] | None,
    active_skills: list[dict[str, Any]] | None = None,
    task_context: dict[str, Any] | None = None,
    project_memory: list[dict[str, Any]] | None = None,
    skill_knowledge: list[dict[str, str]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    model_profile_id: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    privacy_categories: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield native model deltas or one honest buffered result.

    A completed response is never split into fake token chunks.
    """
    input_tokens = model_profiles.estimate_tokens(
        _input_text(user_message, history, draft)
    )
    candidates = _profile_chain(model_profile_id)
    requested_profile_id = candidates[0]["id"] if candidates else model_profile_id
    started = time.perf_counter()
    privacy_kwargs = (
        {
            "conversation_id": conversation_id,
            "request_id": request_id,
            "privacy_categories": privacy_categories,
        }
        if conversation_id or request_id or privacy_categories
        else {}
    )
    for index, profile in enumerate(candidates):
        if (
            not profile.get("enabled")
            or not profile.get("model")
            or model_profiles.limit_reached(profile)
        ):
            continue
        provider = get_provider(profile, **privacy_kwargs)
        fallback_used = index > 0
        if provider is None:
            model_profiles.record_usage(
                profile,
                input_tokens=input_tokens,
                output_tokens=0,
                failed=True,
            )
            continue
        if not provider.native_streaming:
            response = await _respond(
                user_message,
                history,
                draft,
                action,
                active_skills,
                task_context,
                project_memory,
                skill_knowledge,
                attachments,
                profile,
                **(
                    {**privacy_kwargs, "record_privacy": False}
                    if privacy_kwargs
                    else {}
                ),
            )
            output_tokens = model_profiles.estimate_tokens(response or "")
            duration_ms = round((time.perf_counter() - started) * 1_000, 2)
            model_profiles.record_usage(
                profile,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                failed=response is None,
            )
            usage = model_profiles.response_usage(
                profile,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                failed=response is None,
                duration_ms=duration_ms,
            )
            if response:
                yield {
                    "type": "buffered_result",
                    "text": response,
                    "stream_mode": "buffered",
                    "profile_id": profile["id"],
                    "requested_profile_id": requested_profile_id,
                    "used_profile_id": profile["id"],
                    "fallback_used": fallback_used,
                    "usage": usage,
                    "latency_ms": duration_ms,
                }
                _LAST_RESPONSE_METADATA.set({
                    "requested_profile_id": requested_profile_id,
                    "used_profile_id": profile["id"],
                    "fallback_used": fallback_used,
                    "latency_ms": duration_ms,
                    "stream_mode": "buffered",
                    "usage": usage,
                })
                return
            continue

        chunks: list[str] = []
        first_token_ms: float | None = None
        try:
            async for delta in _stream_respond(
                user_message,
                history,
                draft,
                action,
                active_skills,
                task_context,
                project_memory,
                skill_knowledge,
                attachments,
                profile,
                **(
                    {**privacy_kwargs, "record_privacy": False}
                    if privacy_kwargs
                    else {}
                ),
            ):
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1_000
                chunks.append(delta)
                yield {
                    "type": "token",
                    "delta": delta,
                    "stream_mode": "native",
                    "profile_id": profile["id"],
                    "requested_profile_id": requested_profile_id,
                    "used_profile_id": profile["id"],
                    "fallback_used": fallback_used,
                }
        except Exception:
            output_tokens = (
                model_profiles.estimate_tokens("".join(chunks)) if chunks else 0
            )
            duration_ms = round((time.perf_counter() - started) * 1_000, 2)
            model_profiles.record_usage(
                profile,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                failed=True,
            )
            if chunks:
                usage = model_profiles.response_usage(
                    profile,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    failed=True,
                    duration_ms=duration_ms,
                    first_token_ms=first_token_ms,
                )
                _LAST_RESPONSE_METADATA.set({
                    "requested_profile_id": requested_profile_id,
                    "used_profile_id": profile["id"],
                    "fallback_used": fallback_used,
                    "latency_ms": duration_ms,
                    "stream_mode": "native_failed",
                    "partial": True,
                    "usage": usage,
                })
                raise
            # It is safe to try the configured fallback only before a token has
            # been shown to the user.
            continue
        output = "".join(chunks)
        output_tokens = model_profiles.estimate_tokens(output)
        duration_ms = round((time.perf_counter() - started) * 1_000, 2)
        model_profiles.record_usage(
            profile,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failed=not bool(output),
        )
        usage = model_profiles.response_usage(
            profile,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failed=not bool(output),
            duration_ms=duration_ms,
            first_token_ms=first_token_ms,
        )
        if output:
            yield {
                "type": "stream_end",
                "text": output,
                "stream_mode": "native",
                "profile_id": profile["id"],
                "requested_profile_id": requested_profile_id,
                "used_profile_id": profile["id"],
                "fallback_used": fallback_used,
                "usage": usage,
                "latency_ms": duration_ms,
            }
            _LAST_RESPONSE_METADATA.set({
                "requested_profile_id": requested_profile_id,
                "used_profile_id": profile["id"],
                "fallback_used": fallback_used,
                "latency_ms": duration_ms,
                "stream_mode": "native",
                "usage": usage,
            })
            return
    unavailable_latency = round((time.perf_counter() - started) * 1_000, 2)
    _LAST_RESPONSE_METADATA.set({
        "requested_profile_id": requested_profile_id,
        "used_profile_id": None,
        "fallback_used": False,
        "latency_ms": unavailable_latency,
        "stream_mode": "unavailable",
        "usage": None,
    })
    yield {
        "type": "unavailable",
        "stream_mode": "unavailable",
        "text": "",
        "profile_id": None,
        "requested_profile_id": requested_profile_id,
        "used_profile_id": None,
        "fallback_used": False,
        "usage": None,
        "latency_ms": unavailable_latency,
    }


async def analyze_image_vlm(
    image_base64: str,
    prompt: str = "Descreva detalhadamente o que você vê nesta imagem.",
    mime_type: str = "image/jpeg",
) -> str | None:
    return await _analyze_image(image_base64, prompt, mime_type)


def is_configured() -> bool:
    return get_provider() is not None
