"""Evidence-aware verification for completed answers.

This module deliberately uses conservative, inspectable heuristics.  It never
turns a single snippet into a "verified" badge and it does not call a model to
grade its own prose.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from .redaction import sanitize_url

_WORD = re.compile(r"[\wÀ-ÿ]{3,}", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_STOP = {
    "ainda", "assim", "como", "com", "das", "dos", "ela", "ele", "eles",
    "entre", "essa", "esse", "esta", "este", "isso", "mais", "mas", "não",
    "nos", "para", "pela", "pelo", "por", "que", "sem", "ser", "sua", "seu",
    "também", "tem", "uma", "você", "the", "and", "for", "from", "that",
    "this", "with",
}


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _WORD.findall(str(value or ""))
        if token.casefold() not in _STOP
    }


def _claim_sentences(text: str) -> list[str]:
    output: list[str] = []
    for raw in _SENTENCE.split(str(text or "").strip()):
        sentence = re.sub(r"\s+", " ", raw).strip(" -\t")
        if len(sentence) < 24 or sentence.endswith("?"):
            continue
        # Pure headings, acknowledgements and first-person intentions are not
        # useful factual claims.
        lowered = sentence.casefold()
        if lowered.startswith(("vou ", "posso ", "obrigado", "claro", "sim,")):
            continue
        output.append(sentence[:2_000])
    return output[:80]


def _source_text(source: dict[str, Any]) -> str:
    return " ".join(
        str(source.get(key) or "")
        for key in ("title", "excerpt", "text", "content", "quote")
    )[:100_000]


def _source_domain(source: dict[str, Any]) -> str | None:
    raw = str(source.get("url") or source.get("source_uri") or "")
    try:
        return (urlparse(raw).hostname or "").casefold() or None
    except ValueError:
        return None


def _public_source(source: dict[str, Any], index: int) -> dict[str, Any]:
    quality = str(source.get("quality") or source.get("source_type") or "full").lower()
    if quality in {"search", "search_snippet", "snippet"}:
        quality = "snippet"
    elif quality not in {"full", "document", "primary", "secondary"}:
        quality = "full" if _source_text(source) else "metadata_only"
    return {
        "id": str(source.get("id") or source.get("document_id") or f"source-{index + 1}")[:160],
        "title": str(source.get("title") or source.get("name") or f"Fonte {index + 1}")[:300],
        "url": sanitize_url(str(source.get("url") or source.get("source_uri") or "")) or None,
        "domain": _source_domain(source),
        "quality": quality,
        "retrieved_at": source.get("retrieved_at"),
    }


def _source_origin(source: dict[str, Any], public: dict[str, Any]) -> str | None:
    if public.get("domain"):
        return f"domain:{public['domain']}"
    document = str(
        source.get("document_id")
        or source.get("source_uri")
        or source.get("id")
        or ""
    ).strip()
    return f"document:{document}" if document else None


def verify(
    answer: str,
    sources: list[dict[str, Any]] | None,
    *,
    require_independent_sources: bool = True,
) -> dict[str, Any]:
    """Classify factual-looking sentences against supplied source contents.

    ``supported`` means that a substantial portion of the sentence appears in
    at least one non-snippet source. ``inference`` means there is related
    evidence but the exact statement is not directly established.
    """
    answer = str(answer or "").strip()
    if not answer:
        raise ValueError("A resposta é obrigatória.")
    bounded_sources = [
        item for item in (sources or [])[:50] if isinstance(item, dict)
    ]
    prepared = [
        {
            "raw": item,
            "public": _public_source(item, index),
            "tokens": _tokens(_source_text(item)),
        }
        for index, item in enumerate(bounded_sources)
    ]
    for source in prepared:
        source["origin"] = _source_origin(source["raw"], source["public"])
    claims: list[dict[str, Any]] = []
    for index, sentence in enumerate(_claim_sentences(answer)):
        claim_tokens = _tokens(sentence)
        matches: list[dict[str, Any]] = []
        for source in prepared:
            if not claim_tokens or not source["tokens"]:
                continue
            overlap = len(claim_tokens & source["tokens"]) / max(1, len(claim_tokens))
            if overlap >= 0.18:
                matches.append({
                    **source["public"],
                    "overlap": round(overlap, 3),
                })
        matches.sort(key=lambda item: item["overlap"], reverse=True)
        strong = [
            item for item in matches
            if item["overlap"] >= 0.56 and item["quality"] != "snippet"
        ]
        related = [
            item for item in matches
            if item["overlap"] >= 0.28 and item["quality"] != "metadata_only"
        ]
        if strong:
            classification = "supported"
            reason = "A afirmação possui correspondência direta em uma fonte lida."
        elif related:
            classification = "inference"
            reason = "As fontes são relacionadas, mas não estabelecem toda a afirmação."
        else:
            classification = "unsupported"
            reason = "Nenhuma evidência suficiente foi localizada nas fontes fornecidas."
        claims.append({
            "id": f"claim-{index + 1}",
            "text": sentence,
            "classification": classification,
            "reason": reason,
            "sources": matches[:5],
        })

    counts = Counter(item["classification"] for item in claims)
    full_origins = {
        item["origin"]
        for item in prepared
        if item["origin"]
        and item["public"]["quality"] not in {"snippet", "metadata_only"}
    }
    only_snippets = bool(prepared) and all(
        item["public"]["quality"] in {"snippet", "metadata_only"}
        for item in prepared
    )
    independent = len(full_origins) >= 2
    all_supported = bool(claims) and counts["supported"] == len(claims)
    verified = bool(
        all_supported
        and not only_snippets
        and (independent or not require_independent_sources)
    )
    limitations: list[str] = []
    if not prepared:
        limitations.append("Nenhuma fonte com conteúdo foi fornecida.")
    if only_snippets:
        limitations.append("Snippets não são suficientes para atribuir o rótulo verificado.")
    if require_independent_sources and not independent:
        limitations.append("São necessárias pelo menos duas origens independentes lidas.")
    if counts["inference"]:
        limitations.append("Há trechos classificados como inferência.")
    if counts["unsupported"]:
        limitations.append("Há afirmações sem evidência suficiente.")
    return {
        "ok": True,
        "verified": verified,
        "label": "verified" if verified else "not_verified",
        "method": "local_evidence_overlap_v1",
        "claims": claims,
        "summary": {
            "total": len(claims),
            "supported": counts["supported"],
            "inference": counts["inference"],
            "unsupported": counts["unsupported"],
            "independent_origins": len(full_origins),
            "independent_domains": len({
                item["public"]["domain"]
                for item in prepared
                if item["public"]["domain"]
                and item["public"]["quality"] not in {"snippet", "metadata_only"}
            }),
            "only_snippets": only_snippets,
        },
        "limitations": limitations,
        "sources": [item["public"] for item in prepared],
    }
