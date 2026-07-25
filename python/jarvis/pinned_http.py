"""HTTP transport that pins public DNS answers at socket-connect time.

URL pre-validation alone is subject to a DNS-rebinding time-of-check/time-of-use
gap: the HTTP client may resolve the same hostname again after it was approved.
This transport keeps the request origin intact for the HTTP ``Host`` header and
TLS SNI, while its network backend resolves, validates and connects to an IP
literal in one operation.
"""
from __future__ import annotations

from typing import Iterable

import httpcore
import httpx

from .url_security import UnsafeURL, resolve_public_addresses


class PinnedPublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve a host, reject any non-public answer, then dial an IP literal."""

    def __init__(
        self,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = await resolve_public_addresses(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                # Passing a validated IP literal prevents the underlying socket
                # implementation from performing a second DNS lookup.
                return await self._backend.connect_tcp(
                    host=address,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise UnsafeURL("O host da URL não possui um endereço público válido.")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del path, timeout, socket_options
        raise UnsafeURL("Sockets Unix não são permitidos para pesquisa web.")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PinnedPublicAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport backed by :class:`PinnedPublicNetworkBackend`."""

    def __init__(self, *, limits: httpx.Limits | None = None) -> None:
        selected_limits = limits or httpx.Limits(
            max_connections=8,
            max_keepalive_connections=4,
            keepalive_expiry=5.0,
        )
        # AsyncHTTPTransport only relies on ``self._pool`` after construction.
        # Building the pool directly lets us supply the validating network
        # backend while retaining HTTPX's exception and stream adapters.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(verify=True, trust_env=False),
            max_connections=selected_limits.max_connections,
            max_keepalive_connections=selected_limits.max_keepalive_connections,
            keepalive_expiry=selected_limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=0,
            network_backend=PinnedPublicNetworkBackend(),
        )


def create_pinned_public_client(
    *,
    timeout: float = 20,
) -> httpx.AsyncClient:
    """Create a no-proxy client whose connects are pinned to public DNS IPs."""
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=PinnedPublicAsyncHTTPTransport(),
    )
