"""Shared credential redaction for user-visible errors and persistent records."""
from __future__ import annotations

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

REDACTED = "[redigido]"

_SENSITIVE_EXACT_KEYS = {
    "access_key",
    "access_token",
    "api_key",
    "apikey",
    "app_id",
    "appid",
    "auth",
    "auth_token",
    "authorization",
    "client_secret",
    "code",
    "cookie",
    "credential",
    "credentials",
    "encrypted_b64",
    "id_token",
    "key",
    "oauth_token",
    "password",
    "passwd",
    "private_key",
    "proxy_authorization",
    "refresh_token",
    "security_token",
    "secret",
    "set_cookie",
    "sig",
    "signature",
    "token",
    "x_api_key",
    "x_goog_api_key",
}
_SENSITIVE_KEY_PARTS = {
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "passwd",
    "private_key",
    "secret",
    "signature",
    "token",
}
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/\s?#]+@")
_QUERY_PAIR = re.compile(r"([?&;#])([^=&;\s]+)=([^&;\s<>\"'#]+)")
_EMBEDDED_HTTP_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"
_AUTHORIZATION_HEADER = re.compile(
    r"(?i)\b(authorization|proxy[_-]?authorization)\b"
    r"([\"']?\s*[:=]\s*)(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\r\n,;]+)"
)
_COOKIE_HEADER = re.compile(
    r"(?i)\b(cookie|set[_-]?cookie)\b"
    r"([\"']?\s*[:=]\s*)(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\r\n,]+)"
)
_AUTH_SCHEME = re.compile(
    r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}"
)
_CLI_SECRET = re.compile(
    r"(?ix)"
    r"(--(?:"
    r"api[_-]?key|app[_-]?id|appid|authorization|client[_-]?secret|"
    r"cookie|key|password|passwd|private[_-]?key|secret|token"
    r")\b(?:\s*=\s*|\s+))"
    r"(?:(?:bearer|basic)\s+)?"
    r"(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\s,;]+)"
)
_NAMED_SECRET = re.compile(
    r"(?ix)"
    r"\b("
    r"client[_ -]?secret|refresh[_ -]?token|access[_ -]?token|"
    r"id[_ -]?token|security[_ -]?token|api[_ -]?key|"
    r"x[_ -]?api[_ -]?key|x[_ -]?goog[_ -]?api[_ -]?key|"
    r"private[_ -]?key|access[_ -]?key|app[_ -]?id|appid|"
    r"password|passwd|secret|token|signature|credential|auth|key"
    r")\b"
    r"([\"']?\s*[:=]\s*)"
    r"(?!\[redigido\])"
    r"(\"[^\r\n\"]*\"|'[^\r\n']*'|[^\s,;&]+)"
)
_KNOWN_TOKEN_PREFIX = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9_-]{4,}|"
    r"ghp_[A-Za-z0-9_]{4,}|"
    r"github_pat_[A-Za-z0-9_]{4,}|"
    r"AIza[A-Za-z0-9_-]{4,}"
    r")\b"
)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def is_sensitive_field(value: str) -> bool:
    """Return whether a mapping field name conventionally contains a secret."""
    normalized = _normalize_key(value)
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or any(part in normalized for part in _SENSITIVE_KEY_PARTS)
        or normalized.endswith("_key")
    )


def _redact_query(query: str) -> str:
    if not query:
        return query
    parts = re.split(r"([&;])", query)
    for index in range(0, len(parts), 2):
        item = parts[index]
        if "=" not in item:
            continue
        raw_key, _value = item.split("=", 1)
        try:
            decoded_key = unquote_plus(raw_key)
        except (UnicodeDecodeError, ValueError):
            decoded_key = raw_key
        if is_sensitive_field(decoded_key):
            parts[index] = f"{raw_key}={REDACTED}"
    return "".join(parts)


def sanitize_url(value: str) -> str:
    """Redact credentials from one complete HTTP(S) URL."""
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return str(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        return str(value)
    netloc = parsed.netloc
    if parsed.username is not None or parsed.password is not None:
        netloc = netloc.rsplit("@", 1)[-1]
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            _redact_query(parsed.query),
            _redact_query(parsed.fragment),
        )
    )


def _redact_embedded_url(match: re.Match[str]) -> str:
    candidate = match.group(0)
    trailing = ""
    while candidate and candidate[-1] in _TRAILING_URL_PUNCTUATION:
        closing = candidate[-1]
        opening = {")": "(", "]": "[", "}": "{"}.get(closing)
        if opening and candidate.count(opening) >= candidate.count(closing):
            break
        trailing = candidate[-1] + trailing
        candidate = candidate[:-1]
    return sanitize_url(candidate) + trailing


def _redact_query_pair(match: re.Match[str]) -> str:
    raw_key = match.group(2)
    try:
        decoded_key = unquote_plus(raw_key)
    except (UnicodeDecodeError, ValueError):
        decoded_key = raw_key
    if not is_sensitive_field(decoded_key):
        return match.group(0)
    return f"{match.group(1)}{raw_key}={REDACTED}"


def redact_text(value: object) -> str:
    """Redact credentials in free-form text, including embedded URLs."""
    text = _URL_USERINFO.sub(r"\1", str(value))
    text = _QUERY_PAIR.sub(_redact_query_pair, text)
    text = _EMBEDDED_HTTP_URL.sub(_redact_embedded_url, text)
    text = _AUTHORIZATION_HEADER.sub(r"\1\2" + REDACTED, text)
    text = _COOKIE_HEADER.sub(r"\1\2" + REDACTED, text)
    text = _CLI_SECRET.sub(r"\1" + REDACTED, text)
    text = _AUTH_SCHEME.sub(r"\1 " + REDACTED, text)
    text = _NAMED_SECRET.sub(r"\1\2" + REDACTED, text)
    return _KNOWN_TOKEN_PREFIX.sub(REDACTED, text)
