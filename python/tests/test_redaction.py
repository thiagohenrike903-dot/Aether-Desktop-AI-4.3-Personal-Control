from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from jarvis import operations, weather
from jarvis.llm_providers import GeminiProvider, ProviderRequestError
from jarvis.redaction import redact_text


class CredentialRedactionTests(unittest.TestCase):
    def test_embedded_urls_headers_and_named_values_are_redacted(self) -> None:
        values = {
            "weather": "weather-test-credential-123",
            "access": "access-test-credential-456",
            "header": "header-test-credential-789",
            "signed": "signed-test-credential-012",
            "password": "password-test-credential-345",
            "fragment": "fragment-test-credential-678",
            "cli": "cli-test-credential-901",
        }
        message = (
            "Request failed for url "
            f"'https://url-user:{values['password']}@service.invalid/v1"
            f"?view=full&appid={values['weather']}"
            f"&access_token={values['access']}' "
            f"Authorization: Bearer {values['header']}\n"
            f"callback=https://service.invalid/object?X-Amz-Signature={values['signed']} "
            f"redirect=https://service.invalid/callback#access_token={values['fragment']} "
            f"--api-key {values['cli']}"
        )

        redacted = redact_text(message)

        for value in values.values():
            self.assertNotIn(value, redacted)
        self.assertNotIn("url-user", redacted)
        self.assertIn("view=full", redacted)
        self.assertGreaterEqual(redacted.count("[redigido]"), 4)

    def test_operation_payload_redacts_url_inside_exception_sentence(self) -> None:
        credential = "operation-test-credential-123"
        payload = operations.safe_payload({
            "error": (
                "Server error for url "
                f"'https://weather.invalid/forecast?units=metric&appid={credential}'"
            ),
            "status": 500,
        })

        serialized = str(payload)
        self.assertNotIn(credential, serialized)
        self.assertIn("units=metric", serialized)
        self.assertIn("[redigido]", serialized)

    def test_affected_url_redacts_oauth_fragment(self) -> None:
        credential = "fragment-operation-test-credential-123"
        affected = operations.affected_resources({
            "type": "open_url",
            "url": (
                "https://service.invalid/callback"
                f"#access_token={credential}&state=kept"
            ),
        })

        serialized = str(affected)
        self.assertNotIn(credential, serialized)
        self.assertIn("access_token=[redigido]", serialized)
        self.assertIn("state=kept", serialized)

    def test_weather_error_return_does_not_expose_query_credential(self) -> None:
        credential = "weather-return-test-credential-123"

        class FailingClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, url, *, params):
                request = httpx.Request("GET", url, params=params)
                return httpx.Response(503, request=request)

        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": credential}, clear=False),
            patch("jarvis.weather.httpx.AsyncClient", FailingClient),
        ):
            result = asyncio.run(weather.get_forecast("Recife", days=1))

        self.assertFalse(result["ok"])
        self.assertNotIn(credential, result["error"])
        self.assertIn("appid=[redigido]", result["error"])

    def test_provider_logs_sanitized_error_and_keeps_key_out_of_url(self) -> None:
        credential = "provider-test-credential-123"
        leaked_by_upstream = "upstream-test-credential-456"

        class FailingClient:
            request_kwargs = None

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def post(self, url, **kwargs):
                type(self).request_kwargs = kwargs
                request = httpx.Request(
                    "POST",
                    f"{url}?key={leaked_by_upstream}&mode=test",
                )
                return httpx.Response(401, request=request)

        provider = GeminiProvider(credential, "test-model")
        with (
            patch("jarvis.llm_providers.httpx.AsyncClient", FailingClient),
            self.assertLogs("jarvis.llm_providers", level="WARNING") as captured,
        ):
            result = asyncio.run(provider.respond("system", []))

        logs = "\n".join(captured.output)
        self.assertIsNone(result)
        self.assertNotIn(credential, logs)
        self.assertNotIn(leaked_by_upstream, logs)
        self.assertIn("key=[redigido]", logs)
        self.assertEqual(
            FailingClient.request_kwargs["headers"]["x-goog-api-key"],
            credential,
        )
        self.assertNotIn("key", FailingClient.request_kwargs.get("params", {}))

    def test_stream_provider_reraises_only_sanitized_error(self) -> None:
        credential = "stream-upstream-test-credential-123"

        class FailingStream:
            def __init__(self, response):
                self.response = response

            async def __aenter__(self):
                return self.response

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class FailingClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            def stream(self, method, url, **kwargs):
                request = httpx.Request(
                    method,
                    f"{url}?token={credential}&alt=sse",
                )
                return FailingStream(httpx.Response(429, request=request))

        async def consume() -> None:
            provider = GeminiProvider("stream-provider-test-credential", "test-model")
            async for _delta in provider.stream_respond("system", []):
                pass

        with (
            patch("jarvis.llm_providers.httpx.AsyncClient", FailingClient),
            self.assertLogs("jarvis.llm_providers", level="WARNING") as captured,
            self.assertRaises(ProviderRequestError) as raised,
        ):
            asyncio.run(consume())

        self.assertNotIn(credential, str(raised.exception))
        self.assertNotIn(credential, "\n".join(captured.output))
        self.assertIn("token=[redigido]", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
