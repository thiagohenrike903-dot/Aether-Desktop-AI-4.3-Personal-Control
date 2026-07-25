from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if importlib.util.find_spec("httpx") is None:
    httpx = types.ModuleType("httpx")
    httpx.__spec__ = importlib.machinery.ModuleSpec("httpx", loader=None)
    httpx.__aether_test_stub__ = True
    httpx.HTTPError = Exception
    sys.modules["httpx"] = httpx
if importlib.util.find_spec("bs4") is None:
    bs4 = types.ModuleType("bs4")
    bs4.__spec__ = importlib.machinery.ModuleSpec("bs4", loader=None)
    bs4.BeautifulSoup = object
    sys.modules["bs4"] = bs4
if importlib.util.find_spec("psutil") is None:
    psutil = types.ModuleType("psutil")
    psutil.__spec__ = importlib.machinery.ModuleSpec("psutil", loader=None)
    psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    psutil.AccessDenied = type("AccessDenied", (Exception,), {})
    psutil.process_iter = lambda *_args, **_kwargs: []
    sys.modules["psutil"] = psutil

from jarvis import calendar_client, pdf_processor
from jarvis.agents.base import Agent, AgentContext
from jarvis.agents.specialists import files_handler, vision_handler
from jarvis.executor import run as run_action
from jarvis.orchestrator import _memory_safe_action, dispatch


class RoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_short_keyword_does_not_match_inside_another_word(self):
        agent = Agent("designer", "Designer", "Design", keywords=["ui"])
        score = agent.score(AgentContext(user_message="Liste os arquivos em /tmp"))
        self.assertEqual(score, 0.0)

    async def test_generic_prompt_uses_conversation_not_logs(self):
        with (
            patch("jarvis.orchestrator.llm.respond", new=AsyncMock(return_value=None)),
            patch("jarvis.orchestrator.add_turn"),
        ):
            result = await dispatch("Conte uma piada curta", session_id="routing-test")
        self.assertEqual(result["winner"], "conversation")
        self.assertEqual(result["side_effects"][0]["type"], "log")

    async def test_explicit_path_listing_routes_to_files(self):
        with (
            patch("jarvis.orchestrator.llm.respond", new=AsyncMock(return_value=None)),
            patch("jarvis.orchestrator.add_turn"),
        ):
            result = await dispatch(
                "Liste os arquivos em /tmp",
                session_id="files-routing-test",
            )
        self.assertEqual(result["winner"], "files")
        self.assertEqual(result["action"]["type"], "list_directory")
        self.assertEqual(result["action"]["target"], "/tmp")

    async def test_system_analysis_suggestion_is_actionable(self):
        with (
            patch("jarvis.orchestrator.llm.respond", new=AsyncMock(return_value=None)),
            patch("jarvis.orchestrator.add_turn"),
        ):
            result = await dispatch(
                "Analise o uso do meu sistema e me diga se existe algo fora do normal",
                session_id="system-routing-test",
            )
        self.assertEqual(result["winner"], "system")
        self.assertEqual(result["action"]["type"], "system_snapshot")

    async def test_file_conjugations_preserve_source_and_destination(self):
        result = await files_handler(
            AgentContext(user_message='Copie "/tmp/origem.txt" para "/tmp/destino.txt"')
        )
        self.assertEqual(result.action["operation"], "copy")
        self.assertEqual(result.action["source"], "/tmp/origem.txt")
        self.assertEqual(result.action["destination"], "/tmp/destino.txt")

    async def test_image_reference_does_not_capture_screen(self):
        result = await vision_handler(
            AgentContext(user_message="Quero analisar um arquivo de imagem")
        )
        self.assertIsNone(result.action)
        self.assertIn("Anexe", result.reply)


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_screen_capture_requires_confirmation(self):
        result = await run_action({"type": "capture_and_analyze", "prompt": "Veja a tela"})
        self.assertTrue(result["pending_confirmation"])
        self.assertEqual(result["risk"], "high")

    def test_sensitive_action_bodies_are_not_persisted(self):
        safe = _memory_safe_action({
            "type": "email_send",
            "target": "destinatario@example.com",
            "subject": "Assunto",
            "body": "conteúdo confidencial",
            "value": "senha",
        })
        self.assertEqual(safe["type"], "email_send")
        self.assertNotIn("body", safe)
        self.assertNotIn("value", safe)
        self.assertNotIn("subject", safe)


class DocumentAndCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_pdf_upload_rejects_invalid_content(self):
        invalid_base64 = await pdf_processor.extract_text_bytes("não-é-base64", "a.pdf")
        self.assertFalse(invalid_base64["ok"])
        invalid_signature = await pdf_processor.extract_text_bytes("aGVsbG8=", "a.pdf")
        self.assertFalse(invalid_signature["ok"])
        self.assertIn("assinatura", invalid_signature["error"])

    def test_calendar_uses_requested_iana_timezone(self):
        self.assertEqual(calendar_client._resolve_timezone("Asia/Bangkok"), "Asia/Bangkok")
        naive = calendar_client._event_time(
            "2026-07-24T14:30:00",
            "Asia/Bangkok",
        )
        self.assertEqual(naive["timeZone"], "Asia/Bangkok")
        aware = calendar_client._event_time(
            "2026-07-24T14:30:00+07:00",
            "Asia/Bangkok",
        )
        self.assertNotIn("timeZone", aware)

    def test_calendar_rejects_invalid_timezone(self):
        with self.assertRaises(ValueError):
            calendar_client._resolve_timezone("Invalid/Timezone")


if __name__ == "__main__":
    unittest.main()
