from __future__ import annotations

import asyncio
import os
import socket
import ssl
import unittest
from typing import Any
from unittest.mock import patch

import httpcore

from jarvis import browser_agent
from jarvis.pinned_http import (
    PinnedPublicNetworkBackend,
    create_pinned_public_client,
)
from jarvis.url_security import (
    UnsafeURL,
    resolve_public_addresses,
    validate_public_http_url,
)


def _dns_answer(address: str, port: int = 443) -> tuple[Any, ...]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (
        address,
        port,
    )
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


class _RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, stream: httpcore.AsyncNetworkStream | None = None) -> None:
        self.hosts: list[str] = []
        self.stream = stream

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        del port, timeout, local_address, socket_options
        self.hosts.append(host)
        if self.stream is None:
            return object()  # type: ignore[return-value]
        return self.stream

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("Unix sockets must never be used")

    async def sleep(self, seconds: float) -> None:
        del seconds


class _HTTPStream(httpcore.AsyncNetworkStream):
    def __init__(self) -> None:
        self.sni: str | None = None
        self.writes: list[bytes] = []
        self._reads = [
            (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n\r\nOK"
            )
        ]

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        del max_bytes, timeout
        return self._reads.pop(0) if self._reads else b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        del timeout
        self.writes.append(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        del ssl_context, timeout
        self.sni = server_hostname
        return self

    def get_extra_info(self, info: str) -> Any:
        return False if info == "is_readable" else None


class PinnedHTTPTests(unittest.TestCase):
    def test_dns_rebinding_is_checked_again_at_actual_connect(self) -> None:
        public = [_dns_answer("93.184.216.34")]
        rebound_private = [_dns_answer("127.0.0.1")]
        recording = _RecordingBackend()
        backend = PinnedPublicNetworkBackend(recording)
        with patch(
            "jarvis.url_security.socket.getaddrinfo",
            side_effect=[public, rebound_private],
        ):
            accepted = asyncio.run(
                validate_public_http_url("https://research.example/page")
            )
            self.assertEqual(
                accepted,
                "https://research.example/page",
            )
            with self.assertRaises(UnsafeURL):
                asyncio.run(backend.connect_tcp("research.example", 443))
        self.assertEqual(recording.hosts, [])

    def test_mixed_public_private_answer_is_rejected_before_connect(self) -> None:
        answers = [
            _dns_answer("93.184.216.34"),
            _dns_answer("10.20.30.40"),
        ]
        recording = _RecordingBackend()
        backend = PinnedPublicNetworkBackend(recording)
        with patch(
            "jarvis.url_security.socket.getaddrinfo",
            return_value=answers,
        ):
            with self.assertRaises(UnsafeURL):
                asyncio.run(backend.connect_tcp("mixed.example", 443))
        self.assertEqual(recording.hosts, [])

    def test_private_ipv4_mapped_ipv6_is_rejected(self) -> None:
        answers = [_dns_answer("::ffff:127.0.0.1")]
        with patch(
            "jarvis.url_security.socket.getaddrinfo",
            return_value=answers,
        ):
            with self.assertRaises(UnsafeURL):
                asyncio.run(resolve_public_addresses("mapped.example", 443))

    def test_multicast_address_is_not_treated_as_public(self) -> None:
        with patch(
            "jarvis.url_security.socket.getaddrinfo",
            return_value=[_dns_answer("224.0.0.1")],
        ):
            with self.assertRaises(UnsafeURL):
                asyncio.run(resolve_public_addresses("multicast.example", 443))

    def test_socket_connect_uses_ip_but_host_and_sni_use_origin(self) -> None:
        stream = _HTTPStream()
        recording = _RecordingBackend(stream)
        backend = PinnedPublicNetworkBackend(recording)

        async def request() -> tuple[int, bytes]:
            pool = httpcore.AsyncConnectionPool(
                ssl_context=ssl.create_default_context(),
                network_backend=backend,
            )
            try:
                response = await pool.request(
                    "GET",
                    "https://research.example/article",
                )
                return response.status, response.content
            finally:
                await pool.aclose()

        with patch(
            "jarvis.url_security.socket.getaddrinfo",
            return_value=[_dns_answer("93.184.216.34")],
        ):
            status, content = asyncio.run(request())
        self.assertEqual((status, content), (200, b"OK"))
        self.assertEqual(recording.hosts, ["93.184.216.34"])
        self.assertEqual(stream.sni, "research.example")
        self.assertIn(
            b"Host: research.example\r\n",
            b"".join(stream.writes),
        )

    def test_proxy_environment_is_ignored(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:8888",
                "HTTPS_PROXY": "http://127.0.0.1:8888",
                "ALL_PROXY": "socks5://127.0.0.1:1080",
            },
            clear=False,
        ):
            client = create_pinned_public_client()
        try:
            self.assertFalse(client.trust_env)
            self.assertIsNone(client._transport._pool._proxy)
            self.assertEqual(client._mounts, {})
        finally:
            asyncio.run(client.aclose())

    def test_browser_network_actions_fail_closed(self) -> None:
        status = browser_agent.status()
        self.assertFalse(status["enabled"])
        for result in (
            asyncio.run(browser_agent.navigate("https://example.com")),
            asyncio.run(browser_agent.screenshot("https://example.com")),
            asyncio.run(browser_agent.extract_text("https://example.com")),
            asyncio.run(
                browser_agent.click_element("https://example.com", "#button")
            ),
            asyncio.run(
                browser_agent.fill_form("https://example.com", "#field", "value")
            ),
        ):
            self.assertFalse(result["ok"])
            self.assertTrue(result["blocked"])
            self.assertEqual(result["reason"], "egress_proxy_not_pinned")


if __name__ == "__main__":
    unittest.main()
