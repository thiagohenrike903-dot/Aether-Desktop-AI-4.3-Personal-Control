"""Side-by-side model experiments and user-owned quality presets."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import model_profiles
from .config import settings
from .redaction import redact_text

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_CRITERION_IDS = {
    "accuracy", "evidence", "clarity", "completeness", "conciseness",
    "personalization", "safety", "format",
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_lab_presets (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL,
    criteria_json  TEXT NOT NULL,
    protected      INTEGER NOT NULL DEFAULT 0,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS model_lab_runs (
    id                 TEXT PRIMARY KEY,
    preset_id          TEXT,
    prompt              TEXT NOT NULL,
    context_json        TEXT NOT NULL,
    candidates_json     TEXT NOT NULL,
    winner_candidate_id TEXT,
    notes               TEXT NOT NULL DEFAULT '',
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_model_lab_runs_created
ON model_lab_runs(created_at DESC);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _default_criteria() -> list[dict[str, Any]]:
    return [
        {"id": "accuracy", "label": "Correção", "weight": 3, "essential": True},
        {"id": "evidence", "label": "Evidências", "weight": 3, "essential": False},
        {"id": "clarity", "label": "Clareza", "weight": 2, "essential": True},
        {"id": "conciseness", "label": "Objetividade", "weight": 1, "essential": False},
        {"id": "safety", "label": "Segurança", "weight": 3, "essential": True},
    ]


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        now = time.time()
        connection.execute(
            """
            INSERT OR IGNORE INTO model_lab_presets
                (id, name, description, criteria_json, protected, created_at, updated_at)
            VALUES ('balanced-quality', 'Qualidade equilibrada',
                    'Preset local padrão para comparar duas respostas.',
                    ?, 1, ?, ?)
            """,
            (_json(_default_criteria()), now, now),
        )
        connection.commit()


def _clean_criteria(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("Informe pelo menos um critério.")
    output: list[dict[str, Any]] = []
    used: set[str] = set()
    for raw in value[:20]:
        if not isinstance(raw, dict):
            continue
        criterion_id = str(raw.get("id") or "").strip().lower()
        if criterion_id not in _CRITERION_IDS or criterion_id in used:
            raise ValueError(f"Critério inválido: {criterion_id or '(vazio)'}")
        used.add(criterion_id)
        output.append({
            "id": criterion_id,
            "label": str(raw.get("label") or criterion_id).strip()[:120],
            "weight": max(1, min(int(raw.get("weight") or 1), 5)),
            "essential": bool(raw.get("essential", False)),
            "instruction": str(raw.get("instruction") or "")[:1_000],
        })
    if not output:
        raise ValueError("Informe pelo menos um critério válido.")
    return output


def _public_preset(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "criteria": _loads(row["criteria_json"], []),
        "protected": bool(row["protected"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_presets() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM model_lab_presets ORDER BY protected DESC, updated_at DESC"
        ).fetchall()
    return [_public_preset(row) for row in rows]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM model_lab_presets WHERE id = ?", (preset_id,)
        ).fetchone()
    return _public_preset(row) if row else None


def save_preset(
    *,
    name: str,
    criteria: list[dict[str, Any]],
    description: str = "",
    preset_id: str | None = None,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()[:160]
    if not clean_name:
        raise ValueError("O nome do preset é obrigatório.")
    clean = _clean_criteria(criteria)
    existing = get_preset(str(preset_id or "")) if preset_id else None
    if existing and existing["protected"]:
        raise ValueError("O preset padrão é protegido; duplique-o para editar.")
    item_id = str(preset_id or uuid.uuid4())
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO model_lab_presets
                (id, name, description, criteria_json, protected, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                criteria_json = excluded.criteria_json,
                updated_at = excluded.updated_at
            """,
            (item_id, clean_name, str(description or "")[:2_000], _json(clean), now, now),
        )
        connection.commit()
    item = get_preset(item_id)
    assert item is not None
    return item


def _clean_candidate(value: dict[str, Any], index: int) -> dict[str, Any]:
    metrics = value.get("metrics") if isinstance(value.get("metrics"), dict) else {}
    scores = value.get("scores") if isinstance(value.get("scores"), dict) else {}
    return {
        "id": str(value.get("id") or f"candidate-{index + 1}")[:120],
        "profile_id": str(value.get("profile_id") or "")[:120] or None,
        "model": str(value.get("model") or "")[:240] or None,
        "text": redact_text(str(value.get("text") or ""))[:200_000],
        "error": redact_text(str(value.get("error") or ""))[:2_000] or None,
        "metrics": {
            "first_token_ms": (
                max(0.0, float(metrics["first_token_ms"]))
                if metrics.get("first_token_ms") is not None
                else None
            ),
            "first_token_measured": bool(metrics.get("first_token_measured")),
            "duration_ms": max(0.0, float(metrics.get("duration_ms") or 0)),
            "input_tokens": max(0, int(metrics.get("input_tokens") or 0)),
            "output_tokens": max(0, int(metrics.get("output_tokens") or 0)),
            "estimated_cost_usd": max(
                0.0, float(metrics.get("estimated_cost_usd") or 0)
            ),
            "source": "local_measurement_and_estimate",
        },
        "scores": {
            str(key): max(0.0, min(float(score), 5.0))
            for key, score in list(scores.items())[:20]
            if str(key) in _CRITERION_IDS
        },
    }


def _public_run(row: sqlite3.Row) -> dict[str, Any]:
    candidates = _loads(row["candidates_json"], [])
    usable = [
        item for item in candidates
        if isinstance(item, dict)
        and not item.get("error")
        and str(item.get("text") or "").strip()
    ]
    valid = len(usable) == 2
    status = "completed" if valid else ("partial" if usable else "failed")
    return {
        "id": row["id"],
        "preset_id": row["preset_id"],
        "prompt": row["prompt"],
        "context": _loads(row["context_json"], {}),
        "candidates": candidates,
        "valid": valid,
        "status": status,
        "winner_candidate_id": row["winner_candidate_id"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def record_run(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
    preset_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(candidates) != 2:
        raise ValueError("O Model Lab compara exatamente duas respostas por execução.")
    if preset_id and get_preset(preset_id) is None:
        raise KeyError(preset_id)
    clean_prompt = redact_text(str(prompt or "").strip())[:100_000]
    if not clean_prompt:
        raise ValueError("O prompt é obrigatório.")
    clean_candidates = [_clean_candidate(item, i) for i, item in enumerate(candidates)]
    if clean_candidates[0]["id"] == clean_candidates[1]["id"]:
        clean_candidates[1]["id"] = f"{clean_candidates[1]['id']}-b"
    run_id = str(uuid.uuid4())
    now = time.time()
    safe_context = {
        key: value
        for key, value in (context or {}).items()
        if key in {"project_id", "conversation_id", "branch_id", "context_budget"}
    }
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO model_lab_runs
                (id, preset_id, prompt, context_json, candidates_json,
                 winner_candidate_id, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, '', ?, ?)
            """,
            (
                run_id,
                preset_id or "balanced-quality",
                clean_prompt,
                _json(safe_context),
                _json(clean_candidates),
                now,
                now,
            ),
        )
        connection.commit()
    item = get_run(run_id)
    assert item is not None
    return item


def get_run(run_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM model_lab_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return _public_run(row) if row else None


def list_runs(*, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM model_lab_runs ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [_public_run(row) for row in rows]


def select_winner(
    run_id: str,
    candidate_id: str,
    *,
    scores: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    candidate_ids = {item["id"] for item in run["candidates"]}
    if candidate_id not in candidate_ids:
        raise ValueError("A resposta vencedora não pertence a esta comparação.")
    candidates = list(run["candidates"])
    if scores:
        nested_scores = any(isinstance(value, dict) for value in scores.values())
        for item in candidates:
            candidate_scores = (
                scores.get(item["id"])
                if nested_scores
                else scores if item["id"] == candidate_id else None
            )
            if isinstance(candidate_scores, dict):
                item["scores"] = _clean_candidate(
                    {**item, "scores": candidate_scores},
                    0,
                )["scores"]
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE model_lab_runs
            SET candidates_json = ?, winner_candidate_id = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (_json(candidates), candidate_id, str(notes or "")[:4_000], time.time(), run_id),
        )
        connection.commit()
    item = get_run(run_id)
    assert item is not None
    return item


def winner_profile_payload(run_id: str, *, name: str | None = None) -> dict[str, Any]:
    """Return validated fields that app.py can pass to model_profiles.create."""
    run = get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    if not run["winner_candidate_id"]:
        raise ValueError("Escolha uma resposta vencedora primeiro.")
    winner = next(
        item for item in run["candidates"]
        if item["id"] == run["winner_candidate_id"]
    )
    source = model_profiles.get_profile(str(winner.get("profile_id") or ""))
    if source is None:
        raise ValueError("O perfil da resposta vencedora não está mais disponível.")
    return {
        key: value
        for key, value in source.items()
        if key in {
            "description", "provider", "model", "base_url", "temperature",
            "max_tokens", "cost_limit_usd", "cost_input_per_million",
            "cost_output_per_million", "fallback_profile_id", "vision",
            "offline", "enabled",
        }
    } | {
        "name": str(name or f"{source['name']} · Model Lab")[:160],
        "description": (
            f"Perfil reutilizável criado da comparação {run_id[:8]}. "
            f"{source.get('description') or ''}"
        )[:2_000],
    }


_init_db()
