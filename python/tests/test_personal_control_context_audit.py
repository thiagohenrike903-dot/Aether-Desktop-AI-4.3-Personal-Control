from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis import (
    audit_integrity,
    context_inspector,
    operations,
    orchestrator,
)


class ContextExclusionTests(unittest.TestCase):
    def test_every_supported_context_category_can_be_removed_with_reason(self) -> None:
        history = [
            {"id": "message-a", "role": "user", "content": "EXCLUDED_HISTORY"},
            {"id": "message-b", "role": "assistant", "content": "KEPT_HISTORY"},
        ]
        memories = [
            {
                "id": "memory-a",
                "scope": "global",
                "project_id": None,
                "kind": "fact",
                "key": "excluded",
                "value": "EXCLUDED_MEMORY",
            },
            {
                "id": "memory-b",
                "scope": "global",
                "project_id": None,
                "kind": "fact",
                "key": "kept",
                "value": "KEPT_MEMORY",
            },
        ]
        matched_skills = [
            {
                "id": "skill-a",
                "name": "Excluded",
                "version": 1,
                "priority": 10,
                "knowledge_files": [],
            },
            {
                "id": "skill-b",
                "name": "Kept",
                "version": 1,
                "priority": 5,
                "knowledge_files": [],
            },
        ]
        project = {
            "id": "project-a",
            "instructions": "EXCLUDED_INSTRUCTIONS",
        }
        search = {
            "ok": True,
            "grounded": True,
            "results": [
                {
                    "document_id": "document-a",
                    "name": "excluded.txt",
                    "excerpt": "EXCLUDED_DOCUMENT",
                    "citation": {"document_id": "document-a", "chunk": 0},
                },
                {
                    "document_id": "document-b",
                    "name": "kept.txt",
                    "excerpt": "KEPT_DOCUMENT",
                    "citation": {"document_id": "document-b", "chunk": 1},
                },
            ],
            "citations": [],
        }
        metadata = {
            "project_id": "project-a",
            "conversation_id": "conversation-a",
            "attachments": [
                {
                    "id": "attachment-a",
                    "name": "excluded.txt",
                    "kind": "text",
                    "content": "EXCLUDED_ATTACHMENT",
                },
                {
                    "id": "attachment-b",
                    "name": "kept.txt",
                    "kind": "text",
                    "content": "KEPT_ATTACHMENT",
                },
            ],
            "active_task": {"title": "KEPT_TASK_CONTEXT"},
            "context_exclusions": {
                "messages": [{
                    "id": "message-a",
                    "reason": "Usuário removeu a mensagem.",
                }],
                "memories": ["memory-a"],
                "skills": ["skill-a"],
                "documents": ["document-a:0"],
                "attachments": ["attachment-a"],
                "instructions": {
                    "all": True,
                    "reason": "Usuário removeu as instruções.",
                },
            },
        }

        def list_memories(*, scope, **_kwargs):
            return memories if scope == "global" else []

        with (
            patch.object(orchestrator, "_history_for_request", return_value=(history, "conversation")),
            patch.object(orchestrator.skills, "match_skills", return_value=matched_skills),
            patch.object(orchestrator.memory, "list_memories", side_effect=list_memories),
            patch.object(orchestrator.project_library, "get_project", return_value=project),
            patch.object(orchestrator.project_library, "search", return_value=search),
            patch.object(context_inspector, "_profile_chain", return_value=[]),
        ):
            manifest = asyncio.run(
                orchestrator.preview_context("pergunta", metadata=metadata)
            )

        serialized = json.dumps(manifest, ensure_ascii=False)
        for excluded in (
            "EXCLUDED_HISTORY",
            "EXCLUDED_MEMORY",
            "EXCLUDED_DOCUMENT",
            "EXCLUDED_ATTACHMENT",
            "EXCLUDED_INSTRUCTIONS",
        ):
            self.assertNotIn(excluded, serialized)
        self.assertEqual([item["id"] for item in manifest["messages"]], ["message-b"])
        self.assertEqual([item["id"] for item in manifest["memories"]], ["memory-b"])
        self.assertEqual([item["id"] for item in manifest["skills"]], ["skill-b"])
        self.assertEqual(
            [item["document_id"] for item in manifest["documents"]],
            ["document-b"],
        )
        self.assertEqual(
            [item["name"] for item in manifest["attachments"]],
            ["kept.txt"],
        )
        self.assertFalse(manifest["instructions"]["project"])
        self.assertEqual(manifest["limits"]["excluded_by_user"], 6)
        self.assertEqual(
            {item["category"] for item in manifest["omissions"]},
            {
                "messages",
                "memories",
                "skills",
                "documents",
                "attachments",
                "instructions",
            },
        )
        self.assertIn("task_context", manifest["privacy"]["outbound_categories"])


class IntegrityLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "control.sqlite3"
        self.original_operations = operations._DB_PATH
        self.original_audit = audit_integrity._DB_PATH
        operations._DB_PATH = self.path
        audit_integrity._DB_PATH = self.path
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        operations._init_db()
        audit_integrity._init_db()

    def tearDown(self) -> None:
        operations._ACTIONS.clear()
        operations._TASKS.clear()
        operations._DB_PATH = self.original_operations
        audit_integrity._DB_PATH = self.original_audit
        self.temporary.cleanup()

    def test_search_markdown_and_tamper_detection(self) -> None:
        operation = operations.create({
            "type": "email_send",
            "project_id": "project-a",
            "to": "person@example.test",
            "path": "/workspace/report.pdf",
            "url": "https://example.test/send",
            "body": "PRIVATE_BODY",
        })
        operations.transition(operation["id"], "running")
        operations.transition(operation["id"], "completed", result={"ok": True})

        verification = audit_integrity.verify_chain()
        self.assertTrue(verification["valid"])
        self.assertEqual(verification["entries_checked"], 3)
        filtered = audit_integrity.search(
            kind="email_send",
            project_id="project-a",
            resource="report.pdf",
            site="example.test",
            recipient="person@example.test",
        )
        self.assertEqual(filtered["count"], 3)
        transitions = [
            entry["state_change"]
            for entry in filtered["entries"]
            if entry.get("state_change")
        ]
        self.assertTrue(
            any(
                change["before"] == "running"
                and change["after"] == "completed"
                for change in transitions
            )
        )
        serialized = json.dumps(filtered)
        self.assertNotIn("PRIVATE_BODY", serialized)
        report = audit_integrity.markdown_report(project_id="project-a")
        self.assertIn("# Relatório de auditoria do Aether", report)
        self.assertIn("Integridade da cadeia: válida", report)
        self.assertIn("running → completed", report)

        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE audit_integrity_ledger
                SET payload_json = ?
                WHERE sequence = 2
                """,
                ('{"tampered":true}',),
            )
            connection.commit()
        broken = audit_integrity.verify_chain()
        self.assertFalse(broken["valid"])
        self.assertEqual(broken["first_invalid_sequence"], 2)


if __name__ == "__main__":
    unittest.main()
