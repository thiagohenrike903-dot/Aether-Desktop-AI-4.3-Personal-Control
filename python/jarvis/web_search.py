from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from . import privacy_control
from .url_security import UnsafeURL, validate_public_http_url

logger = logging.getLogger("jarvis.web_search")

_MAX_SEARCH_RESULTS = 20
_MAX_QUERY_CHARS = 1000
_MAX_FETCH_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 5


def _network_allowed(
    endpoint: str,
    provider: str,
    conversation_id: str | None = None,
) -> bool:
    decision = privacy_control.network_decision(
        endpoint,
        provider=provider,
        conversation_id=conversation_id,
    )
    if conversation_id:
        privacy_control.record_flow(
            endpoint=endpoint,
            provider=provider,
            categories=[
                "web_query" if provider == "duckduckgo" else "requested_url"
            ],
            conversation_id=conversation_id,
            decision=decision,
        )
    if decision["blocked"]:
        logger.warning(
            "%s bloqueado pelo modo de privacidade: %s",
            provider,
            decision["reason"],
        )
        return False
    return True


def _pinned_client(*, timeout: float) -> httpx.AsyncClient:
    # Keep the transport import lazy so lightweight module discovery still
    # works before the required HTTP dependencies have been installed.
    from .pinned_http import create_pinned_public_client
    return create_pinned_public_client(timeout=timeout)


async def search_duckduckgo(
    query: str,
    max_results: int = 8,
    *,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    query = str(query or "").strip()[:_MAX_QUERY_CHARS]
    max_results = max(1, min(int(max_results), _MAX_SEARCH_RESULTS))
    if not query:
        return []
    if not _network_allowed(
        "https://duckduckgo.com",
        "duckduckgo",
        conversation_id,
    ):
        return []
    try:
        from duckduckgo_search import DDGS
        def _search() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
                    if len(results) >= max_results:
                        break
            return results
        return await asyncio.to_thread(_search)
    except ImportError:
        logger.warning("duckduckgo_search not installed, falling back to httpx")
        return await _search_fallback(
            query,
            max_results,
            conversation_id=conversation_id,
        )
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return await _search_fallback(
            query,
            max_results,
            conversation_id=conversation_id,
        )


async def _search_fallback(
    query: str,
    max_results: int = 8,
    *,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    query = str(query or "").strip()[:_MAX_QUERY_CHARS]
    max_results = max(1, min(int(max_results), _MAX_SEARCH_RESULTS))
    if not query:
        return []
    url = "https://html.duckduckgo.com/html/"
    if not _network_allowed(url, "duckduckgo", conversation_id):
        return []
    params = {"q": query}
    try:
        async with _pinned_client(timeout=15) as client:
            response = await client.post(url, data=params)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict[str, Any]] = []
        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": title_el.get("href", ""),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
        return results
    except Exception as exc:
        logger.error("Fallback search failed: %s", exc)
        return []


async def fetch_page_text(
    url: str,
    max_chars: int = 8000,
    *,
    conversation_id: str | None = None,
) -> str | None:
    max_chars = max(1, min(int(max_chars), 50_000))
    if not _network_allowed(url, "web_fetch", conversation_id):
        return None
    try:
        current_url = await validate_public_http_url(url)
        payload = b""
        async with _pinned_client(timeout=20) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                async with client.stream(
                    "GET",
                    current_url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,text/plain,application/xhtml+xml,application/json,application/xml;q=0.8",
                    },
                ) as response:
                    if response.is_redirect:
                        if redirect_count >= _MAX_REDIRECTS:
                            raise UnsafeURL("A URL excedeu o limite de redirecionamentos.")
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = await validate_public_http_url(
                            urljoin(str(response.url), location)
                        )
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        allowed in content_type
                        for allowed in (
                            "text/",
                            "application/xhtml+xml",
                            "application/json",
                            "application/xml",
                        )
                    ):
                        logger.warning("Blocked non-text response from %s", current_url)
                        return None
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > _MAX_FETCH_BYTES:
                                logger.warning("Blocked oversized response from %s", current_url)
                                return None
                        except ValueError:
                            pass
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > _MAX_FETCH_BYTES:
                            logger.warning("Blocked oversized response from %s", current_url)
                            return None
                        chunks.append(chunk)
                    payload = b"".join(chunks)
                    break
            else:  # pragma: no cover - loop always exits by return/break
                return None

        soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:max_chars]
    except UnsafeURL as exc:
        logger.warning("Blocked unsafe URL: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


async def search_and_summarize(
    query: str,
    max_results: int = 5,
    *,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    query = str(query or "").strip()[:_MAX_QUERY_CHARS]
    max_results = max(1, min(int(max_results), _MAX_SEARCH_RESULTS))
    results = await search_duckduckgo(
        query,
        max_results,
        conversation_id=conversation_id,
    )
    return {
        "query": query,
        "results": results,
        "count": len(results),
    }


async def fetch_page_details(
    url: str,
    *,
    max_chars: int = 30_000,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Open one public page and return bounded, source-labelled content."""
    max_chars = max(1_000, min(int(max_chars), 50_000))
    if not _network_allowed(url, "web_fetch", conversation_id):
        return {
            "ok": False,
            "requested_url": url,
            "url": url,
            "domain": urlparse(url).hostname or "",
            "blocked": True,
            "error": "Fonte bloqueada pelo perfil 100% local.",
        }
    try:
        current_url = await validate_public_http_url(url)
        payload = b""
        content_type = ""
        final_url = current_url
        async with _pinned_client(timeout=20) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                async with client.stream(
                    "GET",
                    current_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Aether Research)",
                        "Accept": "text/html,text/plain,application/xhtml+xml,application/json,application/xml;q=0.8",
                    },
                ) as response:
                    if response.is_redirect:
                        if redirect_count >= _MAX_REDIRECTS:
                            raise UnsafeURL("A URL excedeu o limite de redirecionamentos.")
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirecionamento sem destino.")
                        current_url = await validate_public_http_url(
                            urljoin(str(response.url), location)
                        )
                        continue
                    response.raise_for_status()
                    final_url = str(response.url)
                    # Validate the response URL too; some clients normalize it.
                    await validate_public_http_url(final_url)
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not any(
                        allowed in content_type
                        for allowed in (
                            "text/",
                            "application/xhtml+xml",
                            "application/json",
                            "application/xml",
                        )
                    ):
                        raise ValueError("A fonte não retornou conteúdo textual.")
                    length = response.headers.get("content-length")
                    if length and int(length) > _MAX_FETCH_BYTES:
                        raise ValueError("A fonte excede o limite de 2 MB.")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > _MAX_FETCH_BYTES:
                            raise ValueError("A fonte excede o limite de 2 MB.")
                        chunks.append(chunk)
                    payload = b"".join(chunks)
                    break
        decoded = payload.decode("utf-8", errors="replace")
        soup = BeautifulSoup(decoded, "html.parser")
        title_element = soup.find("title")
        heading = soup.find("h1")
        title = (
            title_element.get_text(" ", strip=True)
            if title_element
            else heading.get_text(" ", strip=True) if heading else ""
        )
        date_value: str | None = None
        date_source: str | None = None
        for selector, source in (
            ('meta[property="article:published_time"]', "article:published_time"),
            ('meta[name="date"]', "meta:date"),
            ('meta[itemprop="datePublished"]', "datePublished"),
            ("time[datetime]", "time:datetime"),
        ):
            element = soup.select_one(selector)
            if not element:
                continue
            candidate = element.get("content") or element.get("datetime")
            if candidate:
                date_value = str(candidate)[:120]
                date_source = source
                break
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)[:max_chars]
        return {
            "ok": True,
            "requested_url": url,
            "url": final_url,
            "domain": urlparse(final_url).hostname or "",
            "title": title[:500],
            "date": date_value,
            "date_source": date_source,
            "text": text,
            "content_type": content_type,
            "retrieved_at": time.time(),
            "truncated": len(soup.get_text(separator=" ", strip=True)) > max_chars,
        }
    except (UnsafeURL, ValueError, httpx.HTTPError, OSError) as exc:
        return {
            "ok": False,
            "requested_url": url,
            "url": url,
            "domain": urlparse(url).hostname or "",
            "error": str(exc),
        }


def _detect_numeric_conflicts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect only directly comparable sentences with differing numbers."""
    claims: dict[str, list[dict[str, Any]]] = {}
    sentence_pattern = re.compile(r"[^.!?]{0,220}\d[\d.,%]*[^.!?]{0,120}[.!?]")
    for source in sources:
        for sentence in sentence_pattern.findall(str(source.get("text") or ""))[:100]:
            normalized = re.sub(r"\d[\d.,%]*", "#", sentence.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()
            numbers = tuple(re.findall(r"\d[\d.,%]*", sentence))
            if len(normalized) < 20 or not numbers:
                continue
            claims.setdefault(normalized, []).append({
                "url": source.get("url"),
                "title": source.get("title"),
                "numbers": numbers,
                "excerpt": sentence.strip()[:360],
            })
    conflicts: list[dict[str, Any]] = []
    for signature, items in claims.items():
        distinct = {item["numbers"] for item in items}
        urls = {item["url"] for item in items}
        if len(distinct) > 1 and len(urls) > 1:
            conflicts.append({
                "type": "numeric_claim",
                "signature": signature[:300],
                "sources": items[:6],
            })
    return conflicts[:20]


async def research(
    query: str,
    *,
    max_results: int = 5,
    max_chars_per_source: int = 30_000,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Search, open and analyse public sources instead of trusting snippets."""
    query = str(query or "").strip()[:_MAX_QUERY_CHARS]
    max_results = max(1, min(int(max_results), 8))
    if not query:
        raise ValueError("A consulta é obrigatória.")
    search_results = await search_duckduckgo(
        query,
        max_results,
        conversation_id=conversation_id,
    )
    semaphore = asyncio.Semaphore(3)

    async def open_result(result: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            opened = await fetch_page_details(
                str(result.get("url") or ""),
                max_chars=max_chars_per_source,
                conversation_id=conversation_id,
            )
        opened["search_title"] = result.get("title", "")
        opened["snippet"] = result.get("snippet", "")
        return opened

    opened = await asyncio.gather(
        *(open_result(result) for result in search_results),
    )
    successful = [item for item in opened if item.get("ok")]
    failures = [
        {
            "url": item.get("requested_url") or item.get("url"),
            "domain": item.get("domain"),
            "error": item.get("error") or "Falha desconhecida.",
        }
        for item in opened
        if not item.get("ok")
    ]
    sources: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    query_terms = [
        item
        for item in re.findall(r"\w{2,}", query.lower(), flags=re.UNICODE)
        if item not in {"de", "da", "do", "the", "and", "para", "com"}
    ][:20]
    for index, item in enumerate(successful, start=1):
        citation = {
            "id": index,
            "title": item.get("title") or item.get("search_title") or item["url"],
            "domain": item.get("domain"),
            "date": item.get("date"),
            "url": item["url"],
        }
        citations.append(citation)
        page_text = str(item.get("text") or "")
        lowered = page_text.lower()
        positions = [
            lowered.find(term)
            for term in query_terms
            if lowered.find(term) >= 0
        ]
        start = max(0, (min(positions) if positions else 0) - 220)
        excerpt = page_text[start:start + 1_200].strip()
        matched_terms = [
            term for term in query_terms if term in lowered
        ]
        sources.append({
            **citation,
            "date_source": item.get("date_source"),
            "requested_url": item.get("requested_url"),
            "text": page_text,
            "excerpt": excerpt,
            "matched_terms": matched_terms,
            "snippet": item.get("snippet"),
            "retrieved_at": item.get("retrieved_at"),
            "truncated": item.get("truncated"),
        })
    analysis_mode = "full_pages" if successful else "snippets_only"
    snippet_sources = []
    if analysis_mode == "snippets_only":
        snippet_sources = [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "domain": urlparse(str(result.get("url") or "")).hostname or "",
                "snippet": result.get("snippet", ""),
            }
            for result in search_results
        ]
    return {
        "ok": bool(search_results),
        "query": query,
        "analysis_mode": analysis_mode,
        "sources": sources if successful else snippet_sources,
        "citations": citations,
        "failures": failures,
        "conflicts": _detect_numeric_conflicts(sources),
        "conflict_detection": "comparable_numeric_sentences",
        "analysis": {
            "method": "opened_page_term_retrieval",
            "query_terms": query_terms,
            "source_summaries": [
                {
                    "citation_id": source["id"],
                    "matched_terms": source.get("matched_terms", []),
                    "excerpt": source.get("excerpt", ""),
                }
                for source in sources
            ],
        },
        "searched_count": len(search_results),
        "opened_count": len(successful),
    }
