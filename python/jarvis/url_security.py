"""Validation helpers for server-side access to user-provided URLs.

The desktop core has access to the host network, so accepting an arbitrary URL
would also expose loopback services, private LANs and cloud metadata endpoints.
These helpers intentionally allow only public HTTP(S) destinations.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


MAX_URL_LENGTH = 2048
_LOCAL_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
}


class UnsafeURL(ValueError):
    """Raised when a URL is malformed or resolves to a non-public address."""


def _public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    # ``is_global`` on an IPv4-mapped IPv6 address has varied between Python
    # releases.  Apply the policy to the embedded IPv4 value explicitly so
    # values such as ``::ffff:127.0.0.1`` can never bypass the private-network
    # check.
    effective = address.ipv4_mapped if isinstance(
        address, ipaddress.IPv6Address
    ) and address.ipv4_mapped is not None else address
    return bool(
        effective.is_global
        and not effective.is_private
        and not effective.is_loopback
        and not effective.is_link_local
        and not effective.is_multicast
        and not effective.is_reserved
        and not effective.is_unspecified
    )


def _normalized_hostname(hostname: str) -> str:
    value = str(hostname or "").rstrip(".").casefold()
    if not value:
        raise UnsafeURL("A URL precisa ter um host.")
    if (
        value in _LOCAL_HOSTNAMES
        or value.endswith(".localhost")
        or value.endswith(".local")
        or value.endswith(".internal")
    ):
        raise UnsafeURL("Hosts locais ou privados não são permitidos.")
    return value


async def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve *hostname* once and return only a wholly public address set.

    Callers that create sockets must connect to one of the returned IP literals,
    not resolve the hostname again.  Rejecting the complete answer set when one
    address is private also closes mixed A/AAAA and IPv4-mapped IPv6 bypasses.
    """
    host = _normalized_hostname(hostname)
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        if not _public_address(str(literal)):
            raise UnsafeURL("Endereços IP locais ou privados não são permitidos.")
        return (str(literal),)

    try:
        answers = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            int(port),
            0,
            socket.SOCK_STREAM,
        )
    except (socket.gaierror, OSError) as exc:
        raise UnsafeURL("Não foi possível resolver o host da URL.") from exc

    addresses: list[str] = []
    for answer in answers:
        if not answer or len(answer) < 5 or not answer[4]:
            raise UnsafeURL("O host da URL retornou uma resposta DNS inválida.")
        raw_address = str(answer[4][0]).split("%", 1)[0]
        try:
            normalized = str(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise UnsafeURL(
                "O host da URL retornou um endereço DNS inválido."
            ) from exc
        if not _public_address(normalized):
            raise UnsafeURL("O host resolve para uma rede local ou privada.")
        if normalized not in addresses:
            addresses.append(normalized)
    if not addresses:
        raise UnsafeURL("O host da URL não possui um endereço válido.")
    return tuple(addresses)


async def validate_public_http_url(url: str) -> str:
    """Return a stripped public HTTP(S) URL or raise :class:`UnsafeURL`.

    Every DNS answer is checked. Rejecting the whole hostname when even one
    answer is private avoids dual-stack bypasses where one family points at a
    public address and the other points at loopback or the LAN.
    """
    value = str(url or "").strip()
    if not value:
        raise UnsafeURL("A URL é obrigatória.")
    if len(value) > MAX_URL_LENGTH:
        raise UnsafeURL("A URL é longa demais.")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("A URL é inválida.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeURL("Somente URLs HTTP e HTTPS são permitidas.")
    if not parsed.hostname:
        raise UnsafeURL("A URL precisa ter um host.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("URLs com credenciais embutidas não são permitidas.")

    hostname = _normalized_hostname(parsed.hostname)
    lookup_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    await resolve_public_addresses(hostname, lookup_port)
    return value


def validate_external_open_url(url: str) -> str:
    """Validate a URL that will be delegated to the operating-system browser.

    This does not resolve DNS because the core itself will not fetch the URL,
    but it blocks dangerous custom schemes and embedded credentials.
    """
    value = str(url or "").strip()
    if not value:
        raise UnsafeURL("A URL é obrigatória.")
    if len(value) > MAX_URL_LENGTH:
        raise UnsafeURL("A URL é longa demais.")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise UnsafeURL("A URL é inválida.") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURL("Somente URLs HTTP e HTTPS são permitidas.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("URLs com credenciais embutidas não são permitidas.")
    return value
