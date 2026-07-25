from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis import (
    agent_governance,
    automations,
    calendar_client,
    email_client,
    plugin_system,
    privacy_control,
    safety_mode,
)
from jarvis.agents import AGENT_REGISTRY, AgentContext
from jarvis.config import minimal_subprocess_env, settings


class CredentialEnvironmentTests(unittest.TestCase):
    def test_launch_credentials_are_in_memory_not_process_environment(self) -> None:
        for key in (
            "AETHER_API_TOKEN",
            "GEMINI_API_KEY",
            "LLM_API_KEY",
            "ELEVENLABS_API_KEY",
            "WEATHER_API_KEY",
            "OPENWEATHER_API_KEY",
            "GOOGLE_CLIENT_CREDENTIALS_JSON",
            "GMAIL_OAUTH_TOKEN_JSON",
            "CALENDAR_OAUTH_TOKEN_JSON",
            "AETHER_SECURE_GEMINI_API_KEY",
            "AETHER_SECURE_LLM_API_KEY",
            "AETHER_SECURE_ELEVENLABS_API_KEY",
            "AETHER_SECURE_WEATHER_API_KEY",
            "AETHER_SECURE_GOOGLE_CLIENT_CREDENTIALS_JSON",
            "AETHER_SECURE_GMAIL_OAUTH_TOKEN_JSON",
            "AETHER_SECURE_CALENDAR_OAUTH_TOKEN_JSON",
        ):
            self.assertNotIn(key, os.environ)
        # The values remain available through Settings when they were supplied;
        # this assertion intentionally does not print or compare the secret.
        self.assertTrue(hasattr(settings, "gemini_api_key"))
        self.assertTrue(hasattr(settings, "api_token"))

    def test_minimal_subprocess_environment_rejects_secret_shaped_keys(self) -> None:
        env = minimal_subprocess_env({
            "AETHER_TEST_FLAG": "safe",
            "CUSTOM_API_KEY": "must-not-leak",
            "ACCESS_TOKEN": "must-not-leak",
        })
        self.assertEqual(env["AETHER_TEST_FLAG"], "safe")
        self.assertNotIn("CUSTOM_API_KEY", env)
        self.assertNotIn("ACCESS_TOKEN", env)
        self.assertNotIn("AETHER_API_TOKEN", env)

    def test_vault_enforcement_ignores_legacy_and_file_injected_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "legacy.env"
            env_file.write_text(
                "\n".join([
                    "GEMINI_API_KEY=legacy-file-key",
                    "LLM_API_KEY=legacy-llm-key",
                    "GOOGLE_CLIENT_CREDENTIALS_JSON={\"installed\":{\"client_id\":\"legacy\"}}",
                    "GMAIL_OAUTH_TOKEN_JSON={\"token\":\"legacy-gmail\"}",
                    "CALENDAR_OAUTH_TOKEN_JSON={\"token\":\"legacy-calendar\"}",
                    "AETHER_SECURE_GEMINI_API_KEY=file-bypass-key",
                    "AETHER_SECURE_GMAIL_OAUTH_TOKEN_JSON={\"token\":\"file-bypass\"}",
                ]),
                encoding="utf-8",
            )
            child_env = dict(os.environ)
            child_env.update({
                "AETHER_DESKTOP": "1",
                "AETHER_VAULT_ENFORCED": "1",
                "AETHER_SECURE_GEMINI_API_KEY": "authorized-vault-key",
                "AETHER_SECURE_GOOGLE_CLIENT_CREDENTIALS_JSON": (
                    '{"installed":{"client_id":"authorized-client"}}'
                ),
                "AETHER_SECURE_GMAIL_OAUTH_TOKEN_JSON": (
                    '{"token":"authorized-gmail"}'
                ),
                "GEMINI_API_KEY": "legacy-parent-key",
                "LLM_API_KEY": "legacy-parent-llm-key",
                "GOOGLE_CLIENT_CREDENTIALS_JSON": (
                    '{"installed":{"client_id":"legacy-parent"}}'
                ),
                "GMAIL_OAUTH_TOKEN_JSON": '{"token":"legacy-parent-gmail"}',
                "CALENDAR_OAUTH_TOKEN_JSON": '{"token":"legacy-parent-calendar"}',
                "JARVIS_ENV_FILE": str(env_file),
            })
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json, os; "
                        "from jarvis.config import settings; "
                        "print(json.dumps({"
                        "'vault_won': settings.gemini_api_key == 'authorized-vault-key',"
                        "'blocked_llm_absent': settings.llm_api_key is None,"
                        "'google_vault_won': 'authorized-client' in "
                        "(settings.google_client_credentials_json or ''),"
                        "'gmail_vault_won': 'authorized-gmail' in "
                        "(settings.gmail_oauth_token_json or ''),"
                        "'calendar_denied': settings.calendar_oauth_token_json is None,"
                        "'vault_enforced': settings.vault_enforced,"
                        "'environment_scrubbed': all(key not in os.environ for key in ("
                        "'GEMINI_API_KEY','LLM_API_KEY',"
                        "'GOOGLE_CLIENT_CREDENTIALS_JSON','GMAIL_OAUTH_TOKEN_JSON',"
                        "'CALENDAR_OAUTH_TOKEN_JSON','AETHER_SECURE_GEMINI_API_KEY',"
                        "'AETHER_SECURE_GOOGLE_CLIENT_CREDENTIALS_JSON',"
                        "'AETHER_SECURE_GMAIL_OAUTH_TOKEN_JSON',"
                        "'AETHER_SECURE_CALENDAR_OAUTH_TOKEN_JSON'))"
                        "}))"
                    ),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=child_env,
                capture_output=True,
                text=True,
                check=True,
            )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload, {
            "vault_won": True,
            "blocked_llm_absent": True,
            "google_vault_won": True,
            "gmail_vault_won": True,
            "calendar_denied": True,
            "vault_enforced": True,
            "environment_scrubbed": True,
        })


class OAuthVaultTests(unittest.TestCase):
    def test_gmail_vault_token_stays_in_memory(self) -> None:
        credentials = SimpleNamespace(valid=True)
        with (
            patch.object(settings, "vault_enforced", True),
            patch.object(
                settings,
                "gmail_oauth_token_json",
                '{"token":"authorized-in-memory"}',
            ),
            patch.object(settings, "google_client_credentials_json", None),
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_info",
                return_value=credentials,
            ) as from_info,
            patch(
                "googleapiclient.discovery.build",
                return_value="gmail-service",
            ) as build,
            patch.object(email_client, "_write_token") as write_token,
        ):
            service = email_client._get_gmail_service()

        self.assertEqual(service, "gmail-service")
        from_info.assert_called_once_with(
            {"token": "authorized-in-memory"},
            email_client._SCOPES,
        )
        build.assert_called_once_with("gmail", "v1", credentials=credentials)
        write_token.assert_not_called()

    def test_calendar_vault_token_stays_in_memory(self) -> None:
        credentials = SimpleNamespace(valid=True)
        with (
            patch.object(settings, "vault_enforced", True),
            patch.object(
                settings,
                "calendar_oauth_token_json",
                '{"token":"authorized-in-memory"}',
            ),
            patch.object(settings, "google_client_credentials_json", None),
            patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_info",
                return_value=credentials,
            ) as from_info,
            patch(
                "googleapiclient.discovery.build",
                return_value="calendar-service",
            ) as build,
            patch.object(calendar_client, "_write_token") as write_token,
        ):
            service = calendar_client._get_calendar_service()

        self.assertEqual(service, "calendar-service")
        from_info.assert_called_once_with(
            {"token": "authorized-in-memory"},
            calendar_client._SCOPES,
        )
        build.assert_called_once_with("calendar", "v3", credentials=credentials)
        write_token.assert_not_called()

    def test_vault_denial_never_falls_back_to_legacy_token_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gmail_token = root / "gmail_token.json"
            calendar_token = root / "calendar_token.json"
            gmail_token.write_text(
                json.dumps({"scopes": email_client._SCOPES}),
                encoding="utf-8",
            )
            calendar_token.write_text(
                json.dumps({"scopes": calendar_client._SCOPES}),
                encoding="utf-8",
            )
            with (
                patch.object(settings, "vault_enforced", True),
                patch.object(settings, "gmail_oauth_token_json", None),
                patch.object(settings, "calendar_oauth_token_json", None),
                patch.object(settings, "google_client_credentials_json", None),
                patch.object(email_client, "_TOKEN_FILE", gmail_token),
                patch.object(calendar_client, "_TOKEN_FILE", calendar_token),
                patch.object(calendar_client, "_LEGACY_TOKEN_FILE", gmail_token),
                patch(
                    "google.oauth2.credentials.Credentials.from_authorized_user_file",
                ) as from_file,
            ):
                with self.assertRaisesRegex(RuntimeError, "não autorizada"):
                    email_client._get_gmail_service()
                with self.assertRaisesRegex(RuntimeError, "não autorizada"):
                    calendar_client._get_calendar_service()

        from_file.assert_not_called()


class SafetySuspensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.original_safety_db = safety_mode._DB_PATH
        self.original_automation_db = automations._DB_PATH
        safety_mode._DB_PATH = root / "control.sqlite3"
        automations._DB_PATH = root / "automations.sqlite3"
        safety_mode._init_db()
        automations._init_db()
        safety_mode.set_mode("normal")
        safety_mode.resume_all()
        self.plugins = dict(plugin_system._plugins)
        self.handlers = dict(plugin_system._plugin_handlers)
        plugin_system._plugins.clear()
        plugin_system._plugin_handlers.clear()

    def tearDown(self) -> None:
        plugin_system._plugins.clear()
        plugin_system._plugins.update(self.plugins)
        plugin_system._plugin_handlers.clear()
        plugin_system._plugin_handlers.update(self.handlers)
        safety_mode._DB_PATH = self.original_safety_db
        automations._DB_PATH = self.original_automation_db
        self.temporary.cleanup()

    def test_project_policy_is_a_stricter_ceiling(self) -> None:
        safety_mode.set_project_policy("project-a", "read_only")
        blocked = safety_mode.preview({
            "type": "workspace_write",
            "project_id": "project-a",
        }, confirmed=True)
        readable = safety_mode.preview({
            "type": "system_snapshot",
            "project_id": "project-a",
        }, confirmed=True)
        other_project = safety_mode.preview({
            "type": "workspace_write",
            "project_id": "project-b",
        }, confirmed=True)
        self.assertTrue(blocked["blocked"])
        self.assertEqual(blocked["effective_mode"], "read_only")
        self.assertEqual(blocked["global_mode"], "normal")
        self.assertTrue(readable["allowed"])
        self.assertTrue(other_project["allowed"])
        self.assertTrue(safety_mode.delete_project_policy("project-a"))

    def test_emergency_suspend_unloads_plugins_and_stops_automations(self) -> None:
        calls: list[str] = []

        async def callback(action, confirmed, request_id, force_approval):
            calls.append(action["type"])
            return {"state": "completed", "id": "operation"}

        async def handler(**_kwargs):
            return {"ok": True}

        plugin_system._plugins["demo"] = {
            "name": "Demo",
            "module_path": "",
            "loaded": True,
            "enabled": True,
        }
        plugin_system._plugin_handlers["demo"] = handler
        result = asyncio.run(plugin_system.suspend_all("emergência"))
        self.assertTrue(result["suspended"])
        self.assertEqual(result["unloaded_plugin_ids"], ["demo"])
        self.assertFalse(result["in_flight_terminated"])
        self.assertNotIn("demo", plugin_system._plugin_handlers)
        self.assertTrue(safety_mode.is_suspended("plugins"))
        self.assertTrue(safety_mode.is_suspended("automations"))

        automation = automations.create(
            name="Suspended",
            trigger={"type": "manual"},
            action={"type": "system_snapshot"},
            enabled=True,
            require_approval=False,
        )
        run = asyncio.run(automations.run(automation["id"], callback))
        self.assertEqual(run["state"], "failed")
        self.assertTrue(run["suspended"])
        self.assertEqual(calls, [])
        self.assertEqual(asyncio.run(automations.poll(callback)), [])


class PrivacyControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original = privacy_control._DB_PATH
        privacy_control._DB_PATH = Path(self.temporary.name) / "privacy.sqlite3"
        privacy_control._init_db()
        privacy_control.set_mode("standard")

    def tearDown(self) -> None:
        privacy_control._DB_PATH = self.original
        self.temporary.cleanup()

    def test_destination_uses_validated_endpoint_not_offline_label(self) -> None:
        fake_local = privacy_control.profile_destination({
            "id": "fake",
            "provider": "openai",
            "model": "model",
            "base_url": "https://api.openai.com/v1",
            "offline": True,
            "available": True,
        })
        actual_local = privacy_control.profile_destination({
            "id": "local",
            "provider": "ollama",
            "model": "model",
            "base_url": "http://127.0.0.1:11434",
            "offline": False,
            "available": True,
        })
        self.assertEqual(fake_local["destination"], "external")
        self.assertFalse(fake_local["local"])
        self.assertEqual(actual_local["destination"], "local")
        self.assertTrue(actual_local["local"])

    def test_local_only_blocks_external_and_builds_conversation_map(self) -> None:
        privacy_control.set_mode("local_only")
        external = privacy_control.network_decision(
            "https://api.openai.com/v1",
            provider="openai",
            conversation_id="conversation-a",
        )
        local = privacy_control.network_decision(
            "http://127.0.0.1:11434",
            provider="ollama",
            conversation_id="conversation-a",
        )
        self.assertTrue(external["blocked"])
        self.assertTrue(local["allowed"])
        privacy_control.record_flow(
            endpoint="https://api.openai.com/v1",
            provider="openai",
            categories=["current_message", "active_memories"],
            conversation_id="conversation-a",
            decision=external,
        )
        privacy_control.record_flow(
            endpoint="http://127.0.0.1:11434",
            provider="ollama",
            categories=["current_message"],
            conversation_id="conversation-a",
            decision=local,
        )
        privacy_map = privacy_control.privacy_map("conversation-a")
        self.assertEqual(privacy_map["flow_count"], 2)
        self.assertEqual(privacy_map["blocked_count"], 1)
        self.assertEqual(privacy_map["local_count"], 1)
        self.assertIn("active_memories", privacy_map["outbound_categories"])


class AgentGovernanceTests(unittest.TestCase):
    def test_placeholder_agent_reports_unavailable_instead_of_generic_reply(self) -> None:
        status = agent_governance.status("marketing")
        self.assertEqual(status["status"], "unavailable")
        self.assertFalse(agent_governance.routing_allowed("marketing"))
        result = asyncio.run(
            AGENT_REGISTRY["marketing"].run(
                AgentContext(user_message="Crie uma campanha")
            )
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIn("indisponível", result.reply.lower())
        self.assertTrue(result.error)

    def test_candidate_gate_requires_documented_measurable_contract(self) -> None:
        rejected = agent_governance.gate_manifest({"agent_id": "candidate"})
        self.assertFalse(rejected["eligible"])
        accepted = agent_governance.gate_manifest({
            "agent_id": "candidate",
            "role": "Função comprovadamente única",
            "unique_function": True,
            "input_contract": {"required": ["request"]},
            "output_contract": {"required": ["result", "status"]},
            "permissions": ["read:bounded-resource"],
            "errors": {"unavailable_state": "unavailable"},
            "dependencies": [],
            "evaluation": {
                "real_requests": 5,
                "passed": True,
                "quality_or_speed_gain_measured": True,
                "cases": [
                    {"id": "one", "passed": True},
                    {"id": "two", "passed": True},
                    {"id": "three", "passed": True},
                ],
            },
        })
        self.assertTrue(accepted["eligible"])
        self.assertFalse(accepted["registered"])


if __name__ == "__main__":
    unittest.main()
