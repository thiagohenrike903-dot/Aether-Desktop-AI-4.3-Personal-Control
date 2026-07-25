from __future__ import annotations

import tempfile
import unittest
import sqlite3
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch

from jarvis import (
    evaluations,
    experience_profiles,
    model_lab,
    model_profiles,
    permissions,
    project_library,
    response_verifier,
    safety_mode,
    simulations,
    user_backup,
    workflows,
)
from jarvis.config import settings


class ResponseUsage43Tests(unittest.TestCase):
    def test_response_metrics_are_not_profile_lifetime_totals(self) -> None:
        profile = {
            "id": "balanced",
            "cost_input_per_million": 10.0,
            "cost_output_per_million": 20.0,
        }
        usage = model_profiles.response_usage(
            profile,
            input_tokens=100,
            output_tokens=25,
            duration_ms=875.4,
            first_token_ms=120.2,
        )
        self.assertEqual(usage["scope"], "response")
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["total_tokens"], 125)
        self.assertEqual(usage["duration_ms"], 875.4)
        self.assertEqual(usage["first_token_ms"], 120.2)
        self.assertAlmostEqual(usage["estimated_cost_usd"], 0.0015)


class ResponseVerifier43Tests(unittest.TestCase):
    def test_single_snippet_can_never_be_verified(self) -> None:
        result = response_verifier.verify(
            "A Terra orbita o Sol em aproximadamente 365 dias.",
            [{
                "name": "Busca",
                "url": "https://example.test/search",
                "excerpt": "A Terra orbita o Sol em aproximadamente 365 dias.",
                "quality": "snippet",
            }],
        )
        self.assertFalse(result["verified"])
        self.assertTrue(result["summary"]["only_snippets"])

    def test_two_independent_full_sources_can_verify(self) -> None:
        answer = "A Terra orbita o Sol em aproximadamente 365 dias."
        result = response_verifier.verify(
            answer,
            [
                {
                    "name": "Fonte A",
                    "url": "https://one.example/a",
                    "text": answer,
                    "quality": "full",
                },
                {
                    "name": "Fonte B",
                    "url": "https://two.example/b",
                    "text": answer,
                    "quality": "primary",
                },
            ],
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"]["independent_domains"], 2)

    def test_two_local_documents_count_as_independent_origins(self) -> None:
        answer = "O relatório registra crescimento de 18 por cento no período."
        result = response_verifier.verify(
            answer,
            [
                {
                    "document_id": "report-a",
                    "name": "Relatório A",
                    "text": answer,
                    "quality": "document",
                },
                {
                    "document_id": "report-b",
                    "name": "Relatório B",
                    "text": answer,
                    "quality": "document",
                },
            ],
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["summary"]["independent_origins"], 2)


class PersonalDatabases43Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.originals = {
            "experience": experience_profiles._DB_PATH,
            "workflows": workflows._DB_PATH,
            "model_lab": model_lab._DB_PATH,
            "evaluations": evaluations._DB_PATH,
            "simulations": simulations._DB_PATH,
            "safety": safety_mode._DB_PATH,
            "permissions": permissions._DB_PATH,
            "models": model_profiles._DB_PATH,
        }
        personal = root / "personal.sqlite3"
        control = root / "control.sqlite3"
        experience_profiles._DB_PATH = personal
        workflows._DB_PATH = personal
        model_lab._DB_PATH = personal
        evaluations._DB_PATH = personal
        simulations._DB_PATH = personal
        safety_mode._DB_PATH = control
        permissions._DB_PATH = control
        model_profiles._DB_PATH = control
        experience_profiles._init_db()
        workflows._init_db()
        model_lab._init_db()
        evaluations._init_db()
        simulations._init_db()
        safety_mode._init_db()
        permissions._init_db()
        model_profiles._init_db()

    def tearDown(self) -> None:
        experience_profiles._DB_PATH = self.originals["experience"]
        workflows._DB_PATH = self.originals["workflows"]
        model_lab._DB_PATH = self.originals["model_lab"]
        evaluations._DB_PATH = self.originals["evaluations"]
        simulations._DB_PATH = self.originals["simulations"]
        safety_mode._DB_PATH = self.originals["safety"]
        permissions._DB_PATH = self.originals["permissions"]
        model_profiles._DB_PATH = self.originals["models"]
        self.temporary.cleanup()

    def test_work_study_personal_layouts_are_independent(self) -> None:
        work = experience_profiles.update_profile(
            "work",
            {"reading": {"width": "wide", "font": "system"}},
        )
        study = experience_profiles.update_profile(
            "study",
            {"reading": {"width": "narrow", "font": "accessible"}},
        )
        self.assertNotEqual(work["reading"]["width"], study["reading"]["width"])
        self.assertNotEqual(work["reading"]["font"], study["reading"]["font"])
        self.assertEqual(experience_profiles.set_active("study")["id"], "study")

    def test_workflow_revisions_and_secret_defaults(self) -> None:
        workflow = workflows.create_workflow(
            name="Enviar resumo",
            steps=[{
                "action": {
                    "type": "email_send",
                    "to": "${recipient}",
                    "body": "${body}",
                }
            }],
            variables=[
                {"name": "recipient", "type": "string"},
                {"name": "body", "type": "string"},
            ],
        )
        updated = workflows.update_workflow(
            workflow["id"],
            {"name": "Enviar resumo aprovado"},
        )
        self.assertEqual(updated["version"], 2)
        self.assertEqual(len(workflows.list_revisions(workflow["id"])), 1)
        protected = workflows.create_workflow(
            name="Protegido",
            steps=[{
                "action": {
                    "type": "web_fetch",
                    "api_key": "sk-this-must-not-be-stored",
                }
            }],
        )
        self.assertEqual(protected["steps"][0]["action"]["api_key"], "${api_key}")
        self.assertTrue(
            next(
                item for item in protected["variables"]
                if item["name"] == "api_key"
            )["secret"]
        )

    def test_model_lab_records_metrics_and_winner(self) -> None:
        run = model_lab.record_run(
            prompt="Compare",
            candidates=[
                {
                    "id": "left",
                    "profile_id": "fast",
                    "text": "Resposta A",
                    "metrics": {
                        "duration_ms": 20,
                        "first_token_ms": 5,
                        "first_token_measured": True,
                    },
                },
                {
                    "id": "right",
                    "profile_id": "balanced",
                    "text": "Resposta B",
                    "metrics": {"duration_ms": 30},
                },
            ],
        )
        selected = model_lab.select_winner(
            run["id"],
            "right",
            scores={
                "left": {"accuracy": 3, "clarity": 4},
                "right": {"accuracy": 5, "clarity": 5},
            },
            notes="Escolha manual do usuário.",
        )
        self.assertEqual(selected["winner_candidate_id"], "right")
        self.assertEqual(selected["candidates"][0]["scores"]["accuracy"], 3)
        self.assertEqual(selected["candidates"][1]["scores"]["accuracy"], 5)
        self.assertEqual(selected["notes"], "Escolha manual do usuário.")
        self.assertFalse(selected["candidates"][1]["metrics"]["first_token_measured"])

    def test_simulation_requires_matching_hash_before_conversion(self) -> None:
        simulation = simulations.create(
            name="Pesquisa local",
            steps=[{
                "name": "Pesquisar",
                "action": {"type": "workspace_search", "query": "Aether"},
            }],
        )
        with self.assertRaises(ValueError):
            simulations.approve(simulation["id"], state_hash="wrong")
        approved = simulations.approve(
            simulation["id"],
            state_hash=simulation["state_hash"],
        )
        self.assertTrue(approved["approved"])
        workflow = simulations.convert_to_workflow(simulation["id"])
        self.assertFalse(workflow["enabled"])

    def test_simulation_never_persists_secret_and_detects_changed_file(self) -> None:
        root = Path(self.temporary.name)
        target = root / "draft.txt"
        target.write_text("before", encoding="utf-8")
        with patch("jarvis.simulations.workspace.get_root", return_value=root):
            simulation = simulations.create(
                name="Prévia segura",
                steps=[{
                    "name": "Atualizar",
                    "action": {
                        "type": "workspace_write",
                        "path": str(target),
                        "content": "after",
                        "api_key": "sk-never-persist-this-value",
                    },
                }],
            )
            persisted = simulations.get(simulation["id"])
            self.assertEqual(
                persisted["steps"][0]["action"]["api_key"],
                "${api_key}",
            )
            self.assertNotIn(
                "sk-never-persist-this-value",
                str(persisted),
            )
            target.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mudou"):
                simulations.approve(
                    simulation["id"],
                    state_hash=simulation["state_hash"],
                )

    def test_release_gate_blocks_essential_regression(self) -> None:
        gate = evaluations.release_gate(
            {"quality": 0.70, "interventions": 1},
            {
                "quality": {
                    "direction": "min",
                    "value": 0.72,
                    "essential": True,
                }
            },
            baseline={"quality": 0.90},
        )
        self.assertFalse(gate["activation_allowed"])

    def test_release_gate_applies_five_percent_limit_to_max_metrics(self) -> None:
        gate = evaluations.release_gate(
            {"quality": 1, "latency_ms": 500},
            {
                "quality": {"value": 0.72, "essential": True},
                "latency_ms": {"value": 1_000, "essential": True},
            },
            baseline={"quality": 1, "latency_ms": 100},
        )
        latency = next(
            item for item in gate["checks"] if item["metric"] == "latency_ms"
        )
        self.assertFalse(latency["passed"])
        self.assertFalse(gate["activation_allowed"])

    def test_confirm_all_guards_new_control_plane_mutations(self) -> None:
        from jarvis.app import app

        safety_mode.set_mode("confirm_all")
        with TestClient(app) as client:
            pending = client.post(
                "/experience-profiles",
                json={"name": "Sem aprovação"},
            )
            self.assertEqual(pending.status_code, 428)
            approved = client.post(
                "/experience-profiles",
                json={"name": "Aprovado"},
                headers={"X-Aether-Confirmed": "true"},
            )
            self.assertEqual(approved.status_code, 200)

    def test_read_only_mode_can_only_be_lowered_after_confirmation(self) -> None:
        from jarvis.app import app

        safety_mode.set_mode("read_only")
        with TestClient(app) as client:
            pending = client.put("/safety-mode", json={"mode": "normal"})
            self.assertEqual(pending.status_code, 428)
            approved = client.put(
                "/safety-mode",
                json={"mode": "normal"},
                headers={"X-Aether-Confirmed": "true"},
            )
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["safety"]["mode"], "normal")


class ProjectLibrary43Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original = project_library._DB_PATH
        project_library._DB_PATH = Path(self.temporary.name) / "projects.sqlite3"
        project_library._init_db()
        self.project = project_library.create_project("Test")

    def tearDown(self) -> None:
        project_library._DB_PATH = self.original
        self.temporary.cleanup()

    def test_duplicate_detection_and_versions(self) -> None:
        first = project_library.import_bytes(
            self.project["id"],
            raw=b"alpha document",
            name="guide.txt",
        )
        duplicate = project_library.import_bytes(
            self.project["id"],
            raw=b"alpha document",
            name="copy.txt",
        )
        second_version = project_library.import_bytes(
            self.project["id"],
            raw=b"alpha document updated",
            name="guide.txt",
        )
        self.assertEqual(duplicate["id"], first["id"])
        self.assertTrue(duplicate["duplicate"])
        self.assertNotEqual(second_version["id"], first["id"])
        versions = project_library.find_duplicates(self.project["id"])
        self.assertEqual(versions["version_group_count"], 1)
        self.assertEqual(
            project_library.index_status(self.project["id"])["status"],
            "ready",
        )


class UserBackup43Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.original_data_dir = settings.data_dir
        self.original_backup_dir = user_backup._BACKUP_DIR
        settings.data_dir = root
        user_backup._BACKUP_DIR = root / "user_backups"
        database = sqlite3.connect(root / "projects.sqlite3")
        database.execute("CREATE TABLE projects (id TEXT PRIMARY KEY)")
        database.execute("INSERT INTO projects VALUES ('one')")
        database.commit()
        database.close()
        (root / "gmail_token.json").write_text("secret", encoding="utf-8")

    def tearDown(self) -> None:
        settings.data_dir = self.original_data_dir
        user_backup._BACKUP_DIR = self.original_backup_dir
        self.temporary.cleanup()

    def test_preview_and_encrypted_validation_exclude_credentials(self) -> None:
        preview = user_backup.preview(["projects"])
        self.assertFalse(preview["credentials_included"])
        backup = user_backup.create(
            components=["projects"],
            password="a-strong-backup-password",
            app_version="4.3.0",
        )
        validated = user_backup.validate(
            backup["filename"],
            password="a-strong-backup-password",
        )
        self.assertTrue(validated["ok"])
        self.assertFalse(validated["credentials_included"])


if __name__ == "__main__":
    unittest.main()
