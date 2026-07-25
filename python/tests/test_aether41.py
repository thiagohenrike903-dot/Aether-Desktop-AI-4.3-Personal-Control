from __future__ import annotations

import asyncio
import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from jarvis import (
    automations,
    conversations,
    llm,
    memory,
    model_profiles,
    operations,
    permissions,
    project_library,
    safety_mode,
    web_search,
    workspace,
)


class TemporaryDatabaseTest(unittest.TestCase):
    MODULES: tuple[object, ...] = ()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.original_paths: list[tuple[object, Path]] = []
        for module in self.MODULES:
            self.original_paths.append((module, module._DB_PATH))
            module._DB_PATH = self.root / f"{module.__name__.rsplit('.', 1)[-1]}.sqlite3"
            module._init_db()

    def tearDown(self) -> None:
        for module, path in self.original_paths:
            module._DB_PATH = path
        self.temporary.cleanup()


class PermissionAndOperationTests(TemporaryDatabaseTest):
    MODULES = (operations, permissions, safety_mode)

    def setUp(self) -> None:
        super().setUp()
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        permissions.reset_session()
        safety_mode.set_mode("normal")

    def test_session_permission_is_volatile_and_overrides_persisted(self) -> None:
        permissions.set_policy("action:email_send", "block")
        self.assertEqual(permissions.get_mode("action:email_send"), "block")
        permissions.set_policy("action:email_send", "session_allow")
        self.assertEqual(
            permissions.decision("action:email_send", risk="high"),
            "allow",
        )
        self.assertTrue(permissions.list_policies()[0]["session_only"])
        permissions.reset_session()
        # Setting session_allow deliberately removes an older persistent rule.
        self.assertEqual(permissions.get_mode("action:email_send"), "ask")

    def test_retry_rechecks_permission_and_never_uses_truncated_payload(self) -> None:
        action = {
            "type": "email_send",
            "to": "person@example.com",
            "body": "private " * 1_000,
        }
        original = operations.create(action, risk="high")
        operations.transition(original["id"], "failed", error="network")
        permissions.set_policy("action:email_send", "ask")

        async def runner(_action, _confirmed):
            return {"ok": True}

        repeated = asyncio.run(operations.retry(original["id"], runner))
        self.assertEqual(repeated["state"], "awaiting_approval")
        self.assertEqual(repeated["parent_id"], original["id"])

        operations._ACTIONS.clear()  # simulate a process restart
        self.assertFalse(operations.get(original["id"])["can_retry"])
        with self.assertRaises(ValueError):
            asyncio.run(operations.retry(original["id"], runner))

    def test_non_cooperative_action_does_not_claim_immediate_cancel(self) -> None:
        pending = operations.create(
            {"type": "file_operation", "operation": "move", "source": "a", "destination": "b"},
            risk="high",
        )
        self.assertTrue(pending["can_cancel"])  # safe before it starts
        running = operations.transition(pending["id"], "running")
        self.assertFalse(running["can_cancel"])
        with self.assertRaises(ValueError):
            asyncio.run(operations.cancel(pending["id"]))

    def test_restart_expires_nonterminal_operations_without_full_payload(self) -> None:
        pending = operations.create(
            {"type": "email_send", "to": "pending@example.com"},
            risk="high",
        )
        awaiting = operations.create(
            {"type": "email_send", "to": "awaiting@example.com"},
            risk="high",
        )
        operations.mark_awaiting_approval(awaiting["id"])
        running = operations.create(
            {"type": "file_operation", "operation": "move", "source": "a"},
            risk="high",
        )
        operations.transition(running["id"], "running")

        operations._ACTIONS.clear()
        operations._TASKS.clear()
        operations._init_db()

        for operation_id in (pending["id"], awaiting["id"], running["id"]):
            recovered = operations.get(operation_id)
            self.assertEqual(recovered["state"], "failed")
            self.assertFalse(recovered["can_approve"])
            self.assertFalse(recovered["can_retry"])
            self.assertFalse(recovered["can_cancel"])
            self.assertIn("reinício", recovered["error"])
            self.assertEqual(
                operations.events(operation_id)[-1]["type"],
                "restart_recovery",
            )

        live = operations.create(
            {"type": "email_send", "to": "live@example.com"},
            risk="high",
        )
        live = operations.mark_awaiting_approval(live["id"])
        self.assertTrue(live["can_approve"])

    def test_redaction_covers_nested_headers_urls_values_and_errors(self) -> None:
        private_body = "texto pessoal que nunca deve chegar ao sqlite"
        action = {
            "type": "browser_fill",
            "url": "https://example.test/form?access_token=top-secret&view=1",
            "headers": {
                "Authorization": "Bearer private-token",
                "Cookie": "session=private",
                "X-Api-Key": "private-key",
            },
            "client_secret": "oauth-secret",
            "refresh_token": "refresh-secret",
            "value": "password123",
            "body": private_body,
            "content": private_body,
            "text": private_body,
        }
        safe = operations.safe_payload(action)
        serialized = json.dumps(safe)
        for secret in (
            "top-secret",
            "private-token",
            "session=private",
            "private-key",
            "oauth-secret",
            "refresh-secret",
            "password123",
            private_body,
        ):
            self.assertNotIn(secret, serialized)
        item = operations.create(action, risk="high")
        self.assertNotIn(private_body, json.dumps(item["action"]))
        self.assertNotIn("top-secret", json.dumps(item["affected"]))
        failed = operations.transition(
            item["id"],
            "failed",
            error="Authorization: Bearer another-secret",
        )
        self.assertNotIn("another-secret", failed["error"])

    def test_exact_block_beats_session_wildcard(self) -> None:
        permissions.set_policy("action:email_send", "block")
        permissions.set_policy("action:*", "session_allow")
        self.assertEqual(
            permissions.decision("action:email_send", risk="high"),
            "block",
        )


class EditableMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original = memory.settings.short_term_db_path
        memory.settings.short_term_db_path = Path(self.temporary.name) / "memory.sqlite3"
        memory._init_db()

    def tearDown(self) -> None:
        memory.settings.short_term_db_path = self.original
        self.temporary.cleanup()

    def test_disabled_memory_does_not_reach_legacy_context(self) -> None:
        item = memory.create_memory(
            scope="global",
            kind="preference",
            key="tone",
            value="concise",
        )
        self.assertEqual(memory.get_preferences()["tone"], "concise")
        updated = memory.update_memory(item["id"], enabled=False)
        self.assertFalse(updated["enabled"])
        self.assertNotIn("tone", memory.get_preferences())
        self.assertEqual(
            len(memory.list_memories(enabled=False, kind="preference")),
            1,
        )

    def test_fact_can_be_renamed_without_leaving_a_ghost_record(self) -> None:
        item = memory.create_memory(
            scope="global",
            kind="fact",
            key="city",
            value="Recife",
        )
        renamed = memory.update_memory(item["id"], key="home_city")
        self.assertEqual(renamed["id"], "fact:home_city")
        self.assertEqual(memory.get_facts(), {"home_city": "Recife"})
        self.assertTrue(memory.delete_fact("home_city"))
        self.assertEqual(memory.list_memories(), [])


class ConversationTests(TemporaryDatabaseTest):
    MODULES = (conversations,)

    def test_branches_and_cursor_pagination_are_persisted(self) -> None:
        conversation = conversations.create(title="Teste", tags=["a", "a", "b"])
        root = conversations.add_message(
            conversation["id"],
            role="user",
            content="Pergunta",
        )
        conversations.add_message(
            conversation["id"],
            role="assistant",
            content="Resposta A",
            parent_id=root["id"],
            branch_id="branch-a",
        )
        conversations.add_message(
            conversation["id"],
            role="assistant",
            content="Resposta B",
            parent_id=root["id"],
            branch_id="branch-b",
        )
        branch = conversations.list_messages(
            conversation["id"],
            branch_id="branch-b",
        )
        self.assertEqual([item["content"] for item in branch["messages"]], ["Resposta B"])
        first_page = conversations.list_conversations(limit=1)
        self.assertEqual(len(first_page["conversations"]), 1)
        self.assertEqual(first_page["conversations"][0]["tags"], ["a", "b"])

    def test_archive_is_recoverable_and_permanent_delete_is_explicit(self) -> None:
        conversation = conversations.create()
        self.assertTrue(conversations.delete(conversation["id"]))
        self.assertTrue(conversations.get(conversation["id"])["archived"])
        self.assertTrue(conversations.delete(conversation["id"], permanent=True))
        self.assertIsNone(conversations.get(conversation["id"]))


class ProjectLibraryTests(TemporaryDatabaseTest):
    MODULES = (project_library,)

    def setUp(self) -> None:
        super().setUp()
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        self.original_workspace_state = workspace._STATE_FILE
        workspace._STATE_FILE = self.root / "workspace-state.json"
        workspace.set_root(str(self.workspace_root))
        self.project = project_library.create_project(
            "Docs",
            root_path=str(self.workspace_root),
        )

    def tearDown(self) -> None:
        workspace._STATE_FILE = self.original_workspace_state
        super().tearDown()

    def test_csv_import_search_and_citation(self) -> None:
        source = self.workspace_root / "budget.csv"
        source.write_text("item,value\nhosting,42\nocr,18\n", encoding="utf-8")
        document = project_library.import_path(self.project["id"], str(source))
        result = project_library.search(self.project["id"], "hosting 42")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["results"][0]["document_id"], document["id"])
        self.assertEqual(result["citations"][0]["cell_range"], "A1:B3")

    def test_arbitrary_path_read_is_blocked(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("private", encoding="utf-8")
        with self.assertRaises(ValueError):
            project_library.import_path(self.project["id"], str(outside))

    def test_sensitive_paths_cannot_be_imported(self) -> None:
        for name in (
            ".env.production",
            "server.key",
            "credentials.json",
            "secrets.yaml",
        ):
            source = self.workspace_root / name
            source.write_text(f"DO_NOT_INDEX_{name}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensíveis"):
                project_library.import_path(self.project["id"], str(source))

        normal = self.workspace_root / "settings.json"
        normal.write_text('{"theme": "dark"}', encoding="utf-8")
        imported = project_library.import_path(self.project["id"], str(normal))
        self.assertEqual(imported["name"], normal.name)

    def test_folder_import_reports_and_never_indexes_sensitive_files(self) -> None:
        folder = self.workspace_root / "mixed"
        folder.mkdir()
        sensitive_names = {
            ".env.production",
            "server.key",
            "credentials.json",
            "secrets.yaml",
        }
        for name in sensitive_names:
            (folder / name).write_text(
                f"FOLDER_SECRET_{name}",
                encoding="utf-8",
            )
        normal = folder / "guide.md"
        normal.write_text("SAFE_FOLDER_DOCUMENT", encoding="utf-8")

        result = project_library.import_folder(self.project["id"], str(folder))

        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["imported"][0]["name"], normal.name)
        self.assertEqual(result["blocked_count"], len(sensitive_names))
        self.assertEqual(
            {item["path"] for item in result["blocked"]},
            sensitive_names,
        )
        self.assertFalse(
            project_library.search(self.project["id"], "FOLDER_SECRET")["grounded"]
        )
        self.assertTrue(
            project_library.search(self.project["id"], "SAFE_FOLDER_DOCUMENT")["grounded"]
        )

    def test_project_root_cannot_escape_selected_workspace(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace"):
            project_library.create_project("Unsafe", root_path=str(self.root))
        with self.assertRaisesRegex(ValueError, "workspace"):
            project_library.update_project(
                self.project["id"],
                {"root_path": str(self.root)},
            )

    def test_zip_bomb_ratio_is_rejected_before_xml_read(self) -> None:
        bomb = io.BytesIO()
        with zipfile.ZipFile(
            bomb,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr("word/document.xml", b"A" * (2 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "compressão insegura"):
            project_library.import_bytes(
                self.project["id"],
                raw=bomb.getvalue(),
                name="bomb.docx",
            )

    def test_docx_and_xlsx_are_extracted_without_optional_libraries(self) -> None:
        docx = io.BytesIO()
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                (
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:body><w:p><w:r><w:t>Aether DOCX</w:t></w:r></w:p></w:body></w:document>"
                ),
            )
        imported_docx = project_library.import_bytes(
            self.project["id"],
            raw=docx.getvalue(),
            name="guide.docx",
        )
        self.assertEqual(imported_docx["status"], "ready")

        xlsx = io.BytesIO()
        with zipfile.ZipFile(xlsx, "w") as archive:
            archive.writestr(
                "xl/sharedStrings.xml",
                (
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<si><t>Alpha</t></si></sst>"
                ),
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                (
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
                    '<c r="B1"><v>99</v></c></row></sheetData></worksheet>'
                ),
            )
        project_library.import_bytes(
            self.project["id"],
            raw=xlsx.getvalue(),
            name="data.xlsx",
        )
        result = project_library.search(self.project["id"], "Alpha 99")
        self.assertTrue(result["grounded"])
        self.assertIn("cell_range", result["citations"][0])


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_opens_pages_and_reports_failures(self) -> None:
        results = [
            {"title": "One", "url": "https://one.test", "snippet": "one"},
            {"title": "Two", "url": "https://two.test", "snippet": "two"},
        ]
        details = [
            {
                "ok": True,
                "requested_url": "https://one.test",
                "url": "https://one.test/article",
                "domain": "one.test",
                "title": "One full",
                "date": "2026-01-01",
                "date_source": "datePublished",
                "text": "The measured value is 10 units.",
                "retrieved_at": time.time(),
                "truncated": False,
            },
            {
                "ok": False,
                "requested_url": "https://two.test",
                "url": "https://two.test",
                "domain": "two.test",
                "error": "blocked",
            },
        ]
        with (
            patch("jarvis.web_search.search_duckduckgo", new=AsyncMock(return_value=results)),
            patch("jarvis.web_search.fetch_page_details", new=AsyncMock(side_effect=details)),
        ):
            report = await web_search.research("value")
        self.assertEqual(report["analysis_mode"], "full_pages")
        self.assertEqual(report["opened_count"], 1)
        self.assertEqual(report["citations"][0]["url"], "https://one.test/article")
        self.assertEqual(report["failures"][0]["domain"], "two.test")

    async def test_snippets_only_is_labelled_when_no_page_opens(self) -> None:
        result = [{"title": "One", "url": "https://one.test", "snippet": "summary"}]
        with (
            patch("jarvis.web_search.search_duckduckgo", new=AsyncMock(return_value=result)),
            patch(
                "jarvis.web_search.fetch_page_details",
                new=AsyncMock(return_value={"ok": False, "url": result[0]["url"], "error": "no"}),
            ),
        ):
            report = await web_search.research("topic")
        self.assertEqual(report["analysis_mode"], "snippets_only")
        self.assertEqual(report["citations"], [])


class NativeStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_happens_only_before_first_native_token(self) -> None:
        primary = {"id": "primary", "enabled": True, "model": "m1"}
        fallback = {"id": "fallback", "enabled": True, "model": "m2"}

        class Provider:
            native_streaming = True

        async def stream(*args):
            profile = args[-1]
            if profile["id"] == "primary":
                raise RuntimeError("connection failed")
            yield "native"

        with (
            patch("jarvis.llm._profile_chain", return_value=[primary, fallback]),
            patch("jarvis.llm.get_provider", return_value=Provider()),
            patch("jarvis.llm._stream_respond", side_effect=stream),
            patch("jarvis.llm.model_profiles.limit_reached", return_value=False),
            patch(
                "jarvis.llm.model_profiles.record_usage",
                side_effect=lambda profile, **_: {"profile_id": profile["id"]},
            ),
        ):
            events = [
                event
                async for event in llm.stream_respond(
                    "hello",
                    [],
                    "draft",
                    None,
                )
            ]
        token = next(item for item in events if item["type"] == "token")
        self.assertEqual(token["delta"], "native")
        self.assertTrue(token["fallback_used"])
        self.assertEqual(token["requested_profile_id"], "primary")

    async def test_partial_native_stream_failure_is_not_completed(self) -> None:
        profile = {"id": "primary", "enabled": True, "model": "m1"}

        class Provider:
            native_streaming = True

        async def partial(*_args):
            yield "partial"
            raise RuntimeError("socket closed")

        with (
            patch("jarvis.llm._profile_chain", return_value=[profile]),
            patch("jarvis.llm.get_provider", return_value=Provider()),
            patch("jarvis.llm._stream_respond", side_effect=partial),
            patch("jarvis.llm.model_profiles.limit_reached", return_value=False),
            patch(
                "jarvis.llm.model_profiles.record_usage",
                return_value={"profile_id": "primary"},
            ),
        ):
            with self.assertRaises(RuntimeError):
                _ = [
                    event
                    async for event in llm.stream_respond(
                        "hello",
                        [],
                        "draft",
                        None,
                    )
                ]
        self.assertTrue(llm.last_response_metadata()["partial"])


class AutomationTests(TemporaryDatabaseTest):
    MODULES = (automations, operations, permissions, safety_mode)

    def setUp(self) -> None:
        super().setUp()
        operations._ACTIONS.clear()
        permissions.reset_session()
        safety_mode.set_mode("normal")
        self.workspace_root = self.root / "workspace"
        self.workspace_root.mkdir()
        self.original_workspace_state = workspace._STATE_FILE
        workspace._STATE_FILE = self.root / "workspace-state.json"
        workspace.set_root(str(self.workspace_root))
        self.calls: list[tuple] = []

    def tearDown(self) -> None:
        workspace._STATE_FILE = self.original_workspace_state
        super().tearDown()

    async def callback(self, action, confirmed, request_id, force_approval):
        self.calls.append((action, confirmed, request_id, force_approval))
        return {
            "id": f"op-{len(self.calls)}",
            "state": "completed",
            "error": None,
            "finished_at": time.time(),
        }

    def test_file_trigger_is_edge_triggered(self) -> None:
        item = automations.create(
            name="Watch",
            trigger={"type": "file", "path": "ready.txt", "event": "exists"},
            action={"type": "system_snapshot"},
            enabled=True,
            require_approval=False,
        )
        self.assertTrue(item["watch_supported"])
        self.assertEqual(asyncio.run(automations.poll(self.callback)), [])
        (self.workspace_root / "ready.txt").write_text("ready", encoding="utf-8")
        self.assertEqual(len(asyncio.run(automations.poll(self.callback))), 1)
        self.assertEqual(asyncio.run(automations.poll(self.callback)), [])
        self.assertEqual(len(self.calls), 1)

    def test_event_payload_is_redacted_and_require_approval_reaches_callback(self) -> None:
        item = automations.create(
            name="Event",
            trigger={"type": "event", "name": "build.done"},
            action={"type": "system_snapshot"},
            enabled=True,
            require_approval=True,
        )
        runs = asyncio.run(
            automations.emit_event(
                "build.done",
                self.callback,
                payload={"api_key": "secret", "content": "x" * 10_000},
            )
        )
        self.assertEqual(len(runs), 1)
        self.assertTrue(self.calls[0][3])
        stored = automations.list_runs(item["id"])[0]["trigger"]
        self.assertEqual(stored["payload"]["api_key"], "[redigido]")
        self.assertLessEqual(len(stored["payload"]["content"]), 501)

    def test_unsupported_condition_cannot_remain_enabled(self) -> None:
        item = automations.create(
            name="Unsupported",
            trigger={"type": "manual"},
            action={"type": "system_snapshot"},
            enabled=True,
        )
        updated = automations.update(
            item["id"],
            {
                "trigger": {
                    "type": "condition",
                    "condition": "python_eval",
                }
            },
        )
        self.assertFalse(updated["watch_supported"])
        self.assertFalse(updated["enabled"])


class ModelProfileTests(TemporaryDatabaseTest):
    MODULES = (model_profiles,)

    def test_usage_is_explicitly_an_estimate_and_limit_is_enforced(self) -> None:
        profile = model_profiles.update_profile(
            "balanced",
            {
                "cost_input_per_million": 10.0,
                "cost_output_per_million": 20.0,
                "cost_limit_usd": 0.00001,
            },
        )
        usage = model_profiles.record_usage(
            profile,
            input_tokens=100,
            output_tokens=100,
        )
        self.assertEqual(usage["source"], "local_estimate")
        self.assertTrue(model_profiles.limit_reached(profile))


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from jarvis.app import app

        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db_modules = (
            automations,
            conversations,
            model_profiles,
            operations,
            permissions,
            project_library,
            safety_mode,
        )
        self.original_paths = []
        for module in self.db_modules:
            self.original_paths.append((module, module._DB_PATH))
            module._DB_PATH = self.root / f"{module.__name__.rsplit('.', 1)[-1]}.sqlite3"
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
        self.temporary.cleanup()

    def test_control_memory_conversation_project_and_automation_contracts(self) -> None:
        permission = self.client.put(
            "/permissions/action:email_send",
            json={"mode": "block"},
        )
        self.assertEqual(permission.status_code, 200)
        operation = self.client.post(
            "/operations/execute",
            json={"action": {"type": "email_send", "to": "a@example.com"}},
        ).json()["operation"]
        self.assertEqual(operation["state"], "failed")
        legacy = self.client.post(
            "/actions/execute",
            json={
                "action": {"type": "email_send", "to": "a@example.com"},
                "confirmed": True,
            },
        ).json()
        self.assertFalse(legacy["ok"])
        self.assertTrue(legacy["blocked"])
        confused_scope = self.client.post(
            "/operations/execute",
            json={
                "action": {"type": "email_send", "to": "a@example.com"},
                "permission_scope": "action:system_snapshot",
            },
        )
        self.assertEqual(confused_scope.status_code, 400)

        blocked_automation = self.client.post(
            "/automations",
            json={
                "name": "Blocked email",
                "trigger": {"type": "manual"},
                "action": {"type": "email_send", "to": "a@example.com"},
                "require_approval": True,
            },
        ).json()["automation"]
        blocked_run = self.client.post(
            f"/automations/{blocked_automation['id']}/run",
            json={"confirmed": False},
        ).json()["run"]
        self.assertEqual(blocked_run["state"], "failed")

        self.client.put(
            "/permissions/action:system_action",
            json={"mode": "ask"},
        )
        awaiting = self.client.post(
            "/operations/execute",
            json={
                "action": {"type": "system_action", "target": "shutdown"},
                "confirmed": False,
            },
        ).json()["operation"]
        self.assertEqual(awaiting["state"], "awaiting_approval")
        self.client.put(
            "/permissions/action:system_action",
            json={"mode": "block"},
        )
        denied = self.client.post(f"/operations/{awaiting['id']}/approve")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["operation"]["state"], "failed")

        created_memory = self.client.post(
            "/memories",
            json={
                "scope": "global",
                "kind": "preference",
                "key": "language",
                "value": "pt-BR",
            },
        ).json()["memory"]
        disabled = self.client.patch(
            f"/memories/{created_memory['id']}",
            json={"enabled": False},
        ).json()["memory"]
        self.assertFalse(disabled["enabled"])

        conversation = self.client.post(
            "/conversations",
            json={"title": "API"},
        ).json()["conversation"]
        message = self.client.post(
            f"/conversations/{conversation['id']}/messages",
            json={"role": "user", "content": "Olá"},
        ).json()["message"]
        self.assertEqual(message["branch_id"], "main")

        project = self.client.post(
            "/projects",
            json={"name": "API docs"},
        ).json()["project"]
        encoded = __import__("base64").b64encode(
            b"Aether control center operations"
        ).decode()
        document_response = self.client.post(
            f"/projects/{project['id']}/documents/import",
            json={
                "name": "notes.txt",
                "data_base64": encoded,
                "mime_type": "text/plain",
            },
        )
        self.assertEqual(document_response.status_code, 200)
        search = self.client.post(
            f"/projects/{project['id']}/search",
            json={"query": "control center"},
        ).json()
        self.assertTrue(search["grounded"])
        archived = self.client.delete(f"/projects/{project['id']}").json()
        self.assertTrue(archived["archived"])
        self.assertFalse(archived["deleted"])

        automation = self.client.post(
            "/automations",
            json={
                "name": "Manual",
                "trigger": {"type": "manual"},
                "action": {"type": "system_snapshot"},
                "require_approval": True,
            },
        ).json()["automation"]
        simulated = self.client.post(
            f"/automations/{automation['id']}/simulate"
        )
        self.assertEqual(simulated.status_code, 200)
        run = self.client.post(
            f"/automations/{automation['id']}/run",
            json={"confirmed": False},
        ).json()["run"]
        self.assertEqual(run["state"], "awaiting_approval")
        self.assertTrue(self.client.get("/model-profiles").json()["profiles"])

    def test_direct_routes_use_permission_engine_and_publish_coverage(self) -> None:
        self.client.put(
            "/permissions/action:email_send",
            json={"mode": "block"},
        )
        with patch(
            "jarvis.executor.email_client.send_email",
            new=AsyncMock(return_value={"ok": True, "id": "should-not-run"}),
        ) as send:
            blocked = self.client.post(
                "/email/send",
                json={
                    "to": "person@example.com",
                    "subject": "Teste",
                    "body": "privado",
                    "confirmed": True,
                },
            )
        self.assertEqual(blocked.status_code, 403)
        send.assert_not_awaited()
        self.assertEqual(blocked.json()["operation"]["state"], "failed")

        self.client.put(
            "/permissions/action:email_send",
            json={"mode": "session_allow"},
        )
        with patch(
            "jarvis.executor.email_client.send_email",
            new=AsyncMock(return_value={"ok": True, "id": "sent"}),
        ) as send:
            allowed = self.client.post(
                "/email/send",
                json={
                    "to": "person@example.com",
                    "subject": "Teste",
                    "body": "privado",
                    "confirmed": False,
                },
            )
        self.assertEqual(allowed.status_code, 200)
        send.assert_awaited_once()
        self.assertEqual(allowed.json()["operation"]["state"], "completed")
        self.assertNotIn(
            "privado",
            json.dumps(allowed.json()["operation"]["action"]),
        )

        capabilities = self.client.get("/permissions/capabilities").json()
        for category in (
            "email",
            "calendar",
            "plugins",
            "browser",
            "workspace",
            "files",
            "git",
            "os",
            "backup",
            "crypto",
        ):
            self.assertIn(category, capabilities["direct_route_coverage"])

    def test_ephemeral_document_extract_supports_docx_and_xlsx(self) -> None:
        import base64

        docx = io.BytesIO()
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr(
                "word/document.xml",
                (
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    'wordprocessingml/2006/main"><w:body><w:p><w:r>'
                    "<w:t>Conteúdo DOCX selecionado</w:t></w:r></w:p>"
                    "</w:body></w:document>"
                ),
            )
        docx_response = self.client.post(
            "/documents/extract",
            json={
                "name": "selecionado.docx",
                "mime_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                "data_base64": base64.b64encode(docx.getvalue()).decode(),
            },
        )
        self.assertEqual(docx_response.status_code, 200)
        docx_payload = docx_response.json()
        self.assertTrue(docx_payload["ok"])
        self.assertFalse(docx_payload["persisted"])
        self.assertIn("Conteúdo DOCX selecionado", docx_payload["text"])
        self.assertEqual(docx_payload["metadata"]["paragraphs"], 1)

        xlsx = io.BytesIO()
        with zipfile.ZipFile(xlsx, "w") as archive:
            archive.writestr(
                "xl/sharedStrings.xml",
                (
                    '<sst xmlns="http://schemas.openxmlformats.org/'
                    'spreadsheetml/2006/main"><si><t>Planilha Aether</t>'
                    "</si></sst>"
                ),
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                (
                    '<worksheet xmlns="http://schemas.openxmlformats.org/'
                    'spreadsheetml/2006/main"><sheetData><row r="1">'
                    '<c r="A1" t="s"><v>0</v></c><c r="B1"><v>41</v>'
                    "</c></row></sheetData></worksheet>"
                ),
            )
        xlsx_response = self.client.post(
            "/documents/extract",
            json={
                "name": "selecionada.xlsx",
                "mime_type": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                "data_base64": base64.b64encode(xlsx.getvalue()).decode(),
            },
        )
        self.assertEqual(xlsx_response.status_code, 200)
        xlsx_payload = xlsx_response.json()
        self.assertIn("Planilha Aether", xlsx_payload["text"])
        self.assertEqual(xlsx_payload["metadata"]["sheets"], 1)
        self.assertEqual(xlsx_payload["sections"][0]["cell_range"], "A1:B1")

    def test_sse_contract_emits_native_delta_and_terminal_payload(self) -> None:
        async def fake_dispatch(*_args, **_kwargs):
            yield {"type": "status", "stage": "routing", "message": "route"}
            yield {
                "type": "token",
                "delta": "Olá",
                "stream_mode": "native",
                "profile_id": "balanced",
            }
            yield {
                "type": "result",
                "payload": {
                    "reply": "Olá",
                    "action": None,
                    "agents": [],
                    "side_effects": [],
                    "winner": "conversation",
                    "used_skills": [],
                    "used_memories": [],
                    "sources": [],
                    "citations": [],
                    "grounded": False,
                    "model": {"used_profile_id": "balanced"},
                },
                "stream_mode": "native",
                "usage": {"output_tokens": 1},
                "fallback_used": False,
            }

        with patch(
            "jarvis.app.orchestrator.dispatch_stream",
            side_effect=fake_dispatch,
        ):
            response = self.client.post(
                "/chat/stream",
                json={
                    "message": "Oi",
                    "session_id": "api-stream",
                    "request_id": "request-test-123",
                    "execute": False,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertIn("event: token", response.text)
        self.assertIn('"delta": "Olá"', response.text)
        self.assertIn("event: done", response.text)


if __name__ == "__main__":
    unittest.main()
