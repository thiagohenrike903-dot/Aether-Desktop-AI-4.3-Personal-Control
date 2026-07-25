from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from jarvis import (
    automations,
    context_inspector,
    conversations,
    memory,
    model_profiles,
    operations,
    permissions,
    project_library,
    safety_mode,
    workflows,
)
from jarvis.llm_providers import build_contents


class ConversationContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original = conversations._DB_PATH
        conversations._DB_PATH = Path(self.temporary.name) / "conversations.sqlite3"
        conversations._init_db()

    def tearDown(self) -> None:
        conversations._DB_PATH = self.original
        self.temporary.cleanup()

    def test_parent_lineage_and_branch_history_do_not_mix(self) -> None:
        conversation = conversations.create(title="Branches")
        root = conversations.add_message(
            conversation["id"],
            role="user",
            content="root",
            branch_id="main",
        )
        branch_a = conversations.add_message(
            conversation["id"],
            role="assistant",
            content="only-a",
            parent_id=root["id"],
            branch_id="branch-a",
        )
        leaf_a = conversations.add_message(
            conversation["id"],
            role="user",
            content="leaf-a",
            parent_id=branch_a["id"],
            branch_id="branch-a",
        )
        conversations.add_message(
            conversation["id"],
            role="assistant",
            content="only-b",
            parent_id=root["id"],
            branch_id="branch-b",
        )

        lineage = conversations.context_history(
            conversation["id"],
            parent_message_id=leaf_a["id"],
        )
        self.assertEqual(
            [item["content"] for item in lineage],
            ["root", "only-a", "leaf-a"],
        )
        branch = conversations.context_history(
            conversation["id"],
            branch_id="branch-b",
        )
        self.assertEqual([item["content"] for item in branch], ["only-b"])


class ContextInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original_profile_db = model_profiles._DB_PATH
        model_profiles._DB_PATH = Path(self.temporary.name) / "profiles.sqlite3"
        model_profiles._init_db()

    def tearDown(self) -> None:
        model_profiles._DB_PATH = self.original_profile_db
        self.temporary.cleanup()

    def test_manifest_contains_metadata_but_not_context_values(self) -> None:
        manifest = context_inspector.build_manifest(
            user_message="pergunta",
            history=[{
                "id": "message-1",
                "role": "user",
                "content": "PRIVATE_HISTORY_VALUE",
            }],
            history_source="conversation",
            active_memories=[{
                "id": "memory-1",
                "scope": "global",
                "project_id": None,
                "kind": "preference",
                "key": "tone",
                "value": "PRIVATE_MEMORY_VALUE",
            }],
            active_skills=[{
                "id": "skill-1",
                "name": "Writing",
                "version": 1,
                "priority": 10,
            }],
            document_search={
                "results": [{
                    "document_id": "document-1",
                    "name": "guide.txt",
                    "excerpt": "PRIVATE_DOCUMENT_VALUE",
                    "citation": {"chunk": 0, "page": 1},
                }]
            },
            attachments=[{
                "name": "private.txt",
                "mime_type": "text/plain",
                "kind": "text",
                "size": 100,
                "content": "PRIVATE_ATTACHMENT_VALUE",
            }],
            project_id="project-1",
            project_instructions="PRIVATE_PROJECT_INSTRUCTIONS",
            action={
                "type": "email_send",
                "to": "private@example.test",
                "body": "PRIVATE_ACTION_BODY",
                "client_secret": "PRIVATE_SECRET",
            },
        )
        serialized = json.dumps(manifest)
        for private_value in (
            "PRIVATE_HISTORY_VALUE",
            "PRIVATE_MEMORY_VALUE",
            "PRIVATE_DOCUMENT_VALUE",
            "PRIVATE_ATTACHMENT_VALUE",
            "PRIVATE_PROJECT_INSTRUCTIONS",
            "PRIVATE_ACTION_BODY",
            "PRIVATE_SECRET",
            "private@example.test",
        ):
            self.assertNotIn(private_value, serialized)
        self.assertEqual(manifest["messages"][0]["id"], "message-1")
        self.assertEqual(manifest["attachments"][0]["name"], "private.txt")
        self.assertEqual(manifest["estimate"]["source"], "local_estimate")
        self.assertFalse(manifest["privacy"]["full_values_in_manifest"])

    def test_provider_boundary_never_receives_full_action_payload(self) -> None:
        contents = build_contents(
            "Explique a ação.",
            [],
            "Vou preparar o envio.",
            {
                "type": "email_send",
                "to": "person@example.test",
                "body": "TOP_SECRET_BODY",
                "value": "TOP_SECRET_VALUE",
            },
        )
        serialized = json.dumps(contents)
        self.assertNotIn("person@example.test", serialized)
        self.assertNotIn("TOP_SECRET_BODY", serialized)
        self.assertNotIn("TOP_SECRET_VALUE", serialized)
        self.assertIn("sanitized_for_model", serialized)


class AuditExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original = operations._DB_PATH
        operations._DB_PATH = Path(self.temporary.name) / "operations.sqlite3"
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        operations._init_db()

    def tearDown(self) -> None:
        operations._DB_PATH = self.original
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        self.temporary.cleanup()

    def test_export_is_bounded_redacted_and_contains_events(self) -> None:
        item = operations.create({
            "type": "email_send",
            "to": "person@example.test",
            "body": "PRIVATE_BODY",
            "client_secret": "PRIVATE_CLIENT_SECRET",
            "url": "https://example.test/?access_token=PRIVATE_URL_TOKEN",
        })
        operations.transition(
            item["id"],
            "failed",
            error="Authorization: Bearer PRIVATE_ERROR_TOKEN",
        )

        exported = operations.export_audit(limit=10)
        serialized = json.dumps(exported)
        for secret in (
            "PRIVATE_BODY",
            "PRIVATE_CLIENT_SECRET",
            "PRIVATE_URL_TOKEN",
            "PRIVATE_ERROR_TOKEN",
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(exported["format"], "aether-audit-v1")
        self.assertEqual(exported["metadata"]["operation_count"], 1)
        self.assertGreaterEqual(exported["metadata"]["event_count"], 2)
        self.assertEqual(
            len(exported["metadata"]["checksum"]["value"]),
            64,
        )
        self.assertFalse(exported["metadata"]["checksum"]["tamper_proof"])
        self.assertTrue(exported["operations"][0]["events"])
        with self.assertRaises(ValueError):
            operations.export_audit(since=20, until=10)
        with self.assertRaises(ValueError):
            operations.export_audit(since=float("nan"))


class ContextApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from jarvis.app import app

        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.modules = (
            automations,
            conversations,
            model_profiles,
            operations,
            permissions,
            project_library,
            safety_mode,
            workflows,
        )
        self.original_paths: list[tuple[object, Path]] = []
        control_db = self.root / "control_center.sqlite3"
        for module in self.modules:
            self.original_paths.append((module, module._DB_PATH))
            module._DB_PATH = (
                control_db
                if module in {operations, permissions, safety_mode}
                else self.root / f"{module.__name__.rsplit('.', 1)[-1]}.sqlite3"
            )
            module._init_db()
        self.original_memory_path = memory.settings.short_term_db_path
        memory.settings.short_term_db_path = self.root / "memory.sqlite3"
        memory._init_db()
        operations._ACTIONS.clear()
        permissions.reset_session()
        safety_mode.set_mode("normal")
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        for module, path in self.original_paths:
            module._DB_PATH = path
        memory.settings.short_term_db_path = self.original_memory_path
        operations._ACTIONS.clear()
        permissions.reset_session()
        self.temporary.cleanup()

    @staticmethod
    def _chat_result(reply: str = "ok") -> dict:
        return {
            "reply": reply,
            "action": None,
            "agents": [],
            "side_effects": [],
            "winner": "conversation",
            "used_skills": [],
            "used_memories": [],
            "sources": [],
            "citations": [],
            "context_manifest": {"version": 1},
            "grounded": False,
            "model": {},
        }

    def test_chat_inherits_project_and_rejects_conflict(self) -> None:
        conversation = conversations.create(
            title="Project",
            project_id="project-one",
        )
        with patch(
            "jarvis.app.orchestrator.dispatch",
            new=AsyncMock(return_value=self._chat_result()),
        ) as dispatch:
            inherited = self.client.post(
                "/chat",
                json={
                    "message": "Olá",
                    "session_id": "session-project",
                    "conversation_id": conversation["id"],
                    "metadata": {"project_id": "metadata-cannot-override"},
                    "execute": False,
                },
            )
        self.assertEqual(inherited.status_code, 200)
        self.assertEqual(
            dispatch.await_args.kwargs["metadata"]["project_id"],
            "project-one",
        )

        with patch(
            "jarvis.app.orchestrator.dispatch",
            new=AsyncMock(return_value=self._chat_result()),
        ) as dispatch:
            conflict = self.client.post(
                "/chat",
                json={
                    "message": "Olá",
                    "session_id": "session-conflict",
                    "conversation_id": conversation["id"],
                    "project_id": "project-two",
                    "execute": False,
                },
            )
        self.assertEqual(conflict.status_code, 409)
        dispatch.assert_not_awaited()

    def test_stream_persists_server_generated_request_id(self) -> None:
        conversation = conversations.create(title="Streaming")

        async def fake_stream(*_args, **_kwargs):
            yield {
                "type": "result",
                "payload": self._chat_result("streamed"),
                "stream_mode": "native",
                "usage": None,
                "fallback_used": False,
            }

        with patch(
            "jarvis.app.orchestrator.dispatch_stream",
            side_effect=fake_stream,
        ):
            response = self.client.post(
                "/chat/stream",
                json={
                    "message": "stream me",
                    "session_id": "session-stream",
                    "conversation_id": conversation["id"],
                    "execute": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        accepted_data = next(
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        )
        messages = conversations.list_messages(conversation["id"])["messages"]
        saved_user = next(item for item in messages if item["role"] == "user")
        self.assertTrue(saved_user["metadata"]["request_id"])
        self.assertEqual(
            saved_user["metadata"]["request_id"],
            accepted_data["request_id"],
        )

    def test_context_preview_uses_branch_and_has_no_side_effects(self) -> None:
        conversation = conversations.create(title="Preview")
        conversations.add_message(
            conversation["id"],
            role="user",
            content="main value",
            branch_id="main",
        )
        branch = conversations.add_message(
            conversation["id"],
            role="user",
            content="branch private value",
            branch_id="branch-a",
        )
        memory.add_turn(
            "user",
            "legacy session value",
            "preview-session",
        )
        response = self.client.post(
            "/context/preview",
            json={
                "message": "next",
                "session_id": "preview-session",
                "conversation_id": conversation["id"],
                "branch_id": "branch-a",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["side_effects"])
        self.assertEqual(
            [item["id"] for item in payload["context"]["messages"]],
            [branch["id"]],
        )
        self.assertNotIn("branch private value", json.dumps(payload))

    def test_audit_export_endpoint_is_downloadable_json(self) -> None:
        operations.create({"type": "system_snapshot"})
        response = self.client.get("/audit/export?limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.json()["metadata"]["app_version"], "4.3.0")

    def test_safety_endpoints_cover_chat_direct_approve_and_retry(self) -> None:
        current = self.client.get("/safety-mode")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["safety"]["mode"], "normal")
        pending_change = self.client.put(
            "/safety-mode",
            json={"mode": "confirm_all"},
        )
        self.assertEqual(pending_change.status_code, 428)
        changed = self.client.put(
            "/safety-mode",
            json={"mode": "confirm_all"},
            headers={"X-Aether-Confirmed": "true"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(changed.json()["simulation_supported"])
        preview = self.client.post(
            "/safety-mode/preview",
            json={"action": {"type": "system_snapshot"}},
        ).json()["preview"]
        self.assertEqual(preview["decision"], "ask")
        self.assertEqual(preview["classification"], "read")

        with patch(
            "jarvis.app.orchestrator.dispatch",
            new=AsyncMock(return_value={
                **self._chat_result(),
                "action": {"type": "system_snapshot"},
            }),
        ):
            chat = self.client.post(
                "/chat",
                json={
                    "message": "status",
                    "session_id": "safe-chat",
                    "execute": True,
                },
            ).json()
        self.assertEqual(chat["operation"]["state"], "awaiting_approval")

        with patch(
            "jarvis.app.run_action",
            new=AsyncMock(return_value={"ok": True}),
        ) as runner:
            direct = self.client.post(
                "/actions/execute",
                json={"action": {"type": "system_snapshot"}},
            ).json()
            self.assertTrue(direct["pending_confirmation"])
            runner.assert_not_awaited()

            approved = self.client.post(
                f"/operations/{direct['operation_id']}/approve"
            ).json()
            self.assertTrue(approved["ok"])
            runner.assert_awaited_once()

        failed = operations.create(
            {"type": "system_snapshot"},
            risk="low",
        )
        operations.transition(failed["id"], "failed", error="offline")
        retried = self.client.post(
            f"/operations/{failed['id']}/retry"
        ).json()["operation"]
        self.assertEqual(retried["state"], "awaiting_approval")

        self.client.put(
            "/safety-mode",
            json={"mode": "read_only"},
            headers={"X-Aether-Confirmed": "true"},
        )
        with patch(
            "jarvis.app.run_action",
            new=AsyncMock(return_value={"ok": True}),
        ) as runner:
            blocked = self.client.post(
                "/os/volume?level=50&confirmed=true"
            )
        self.assertEqual(blocked.status_code, 403)
        runner.assert_not_awaited()

    def test_project_policy_is_derived_from_body_and_persisted_resources(self) -> None:
        restricted = project_library.create_project("Restricted")
        unrelated = project_library.create_project("Unrelated")
        safety_mode.set_project_policy(restricted["id"], "read_only")

        blocked_create = self.client.post(
            "/conversations",
            json={
                "title": "Must not be created",
                "project_id": restricted["id"],
            },
        )
        self.assertEqual(blocked_create.status_code, 403)

        conversation = conversations.create(
            title="Existing",
            project_id=restricted["id"],
        )
        spoofed_header = self.client.patch(
            f"/conversations/{conversation['id']}",
            json={"title": "Bypass attempt"},
            headers={"X-Aether-Project-Id": unrelated["id"]},
        )
        self.assertEqual(spoofed_header.status_code, 403)
        self.assertEqual(
            conversations.get(conversation["id"])["title"],
            "Existing",
        )

        project_memory = memory.create_memory(
            scope="project",
            project_id=restricted["id"],
            kind="note",
            key="policy-test",
            value="kept",
        )
        blocked_memory = self.client.patch(
            f"/memories/{project_memory['id']}",
            json={"value": "changed"},
        )
        self.assertEqual(blocked_memory.status_code, 403)
        self.assertEqual(memory.get_memory(project_memory["id"])["value"], "kept")

        automation = automations.create(
            name="Project action",
            trigger={"type": "schedule", "interval_seconds": 3600},
            action={
                "type": "system_snapshot",
                "project_id": restricted["id"],
            },
        )
        blocked_automation = self.client.patch(
            f"/automations/{automation['id']}",
            json={"name": "Bypass attempt"},
        )
        self.assertEqual(blocked_automation.status_code, 403)

        safety_mode.set_project_policy(restricted["id"], "confirm_all")
        pending = self.client.post(
            "/conversations",
            json={
                "title": "Needs confirmation",
                "project_id": restricted["id"],
            },
        )
        self.assertEqual(pending.status_code, 428)
        approved = self.client.post(
            "/conversations",
            json={
                "title": "Confirmed",
                "project_id": restricted["id"],
            },
            headers={"X-Aether-Confirmed": "true"},
        )
        self.assertEqual(approved.status_code, 200)

        workflow = workflows.create_workflow(
            name="Restricted workflow",
            steps=[{
                "name": "Inspect",
                "action": {
                    "type": "system_snapshot",
                    "project_id": restricted["id"],
                },
            }],
        )
        workflows.update_workflow(workflow["id"], {"name": "Second version"})
        revision_id = workflows.list_revisions(workflow["id"])[0]["id"]
        safety_mode.set_project_policy(restricted["id"], "read_only")
        for method, path, body in [
            ("PATCH", f"/workflows/{workflow['id']}", {"name": "Bypass"}),
            ("DELETE", f"/workflows/{workflow['id']}", None),
            ("POST", f"/workflows/{workflow['id']}/run", {"values": {}}),
            (
                "POST",
                f"/workflows/{workflow['id']}/restore/{revision_id}",
                {},
            ),
        ]:
            response = self.client.request(method, path, json=body)
            self.assertEqual(response.status_code, 403, path)


if __name__ == "__main__":
    unittest.main()
