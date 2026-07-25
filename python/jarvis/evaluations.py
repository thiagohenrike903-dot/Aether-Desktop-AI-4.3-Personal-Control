"""Personal evaluation sets and conservative release gates."""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings
from .redaction import redact_text

_LOCK = threading.RLock()
_DB_PATH: Path = settings.data_dir / "personal_control.sqlite3"
_METRICS = {"quality", "latency_ms", "estimated_cost_usd", "interventions"}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_cases (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    input_text      TEXT NOT NULL,
    good_example    TEXT NOT NULL,
    bad_example     TEXT NOT NULL,
    essential_terms_json TEXT NOT NULL,
    forbidden_terms_json TEXT NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_presets (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    thresholds_json TEXT NOT NULL,
    protected       INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id              TEXT PRIMARY KEY,
    subject_type    TEXT NOT NULL,
    subject_id      TEXT,
    preset_id       TEXT NOT NULL,
    results_json    TEXT NOT NULL,
    summary_json    TEXT NOT NULL,
    created_at      REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _clean_terms(value: Any) -> list[str]:
    output: list[str] = []
    for raw in value if isinstance(value, list) else []:
        term = str(raw or "").strip()[:160]
        if term and term.casefold() not in {item.casefold() for item in output}:
            output.append(term)
    return output[:50]


def _public_case(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "input": row["input_text"],
        "good_example": row["good_example"],
        "bad_example": row["bad_example"],
        "essential_terms": _loads(row["essential_terms_json"], []),
        "forbidden_terms": _loads(row["forbidden_terms_json"], []),
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_cases(*, enabled: bool | None = None) -> list[dict[str, Any]]:
    where = "" if enabled is None else "WHERE enabled = ?"
    values: list[Any] = [] if enabled is None else [int(enabled)]
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM evaluation_cases {where} ORDER BY updated_at DESC",
            values,
        ).fetchall()
    return [_public_case(row) for row in rows]


def save_case(payload: dict[str, Any]) -> dict[str, Any]:
    item_id = str(payload.get("id") or uuid.uuid4())
    name = str(payload.get("name") or "").strip()[:160]
    input_text = redact_text(str(payload.get("input") or "").strip())[:100_000]
    if not name or not input_text:
        raise ValueError("Nome e solicitação real são obrigatórios.")
    now = time.time()
    existing = next((item for item in list_cases() if item["id"] == item_id), None)
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_cases (
                id, name, input_text, good_example, bad_example,
                essential_terms_json, forbidden_terms_json, enabled,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                input_text = excluded.input_text,
                good_example = excluded.good_example,
                bad_example = excluded.bad_example,
                essential_terms_json = excluded.essential_terms_json,
                forbidden_terms_json = excluded.forbidden_terms_json,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                item_id, name, input_text,
                redact_text(str(payload.get("good_example") or ""))[:200_000],
                redact_text(str(payload.get("bad_example") or ""))[:200_000],
                _json(_clean_terms(payload.get("essential_terms"))),
                _json(_clean_terms(payload.get("forbidden_terms"))),
                int(bool(payload.get("enabled", True))),
                existing["created_at"] if existing else now,
                now,
            ),
        )
        connection.commit()
    return next(item for item in list_cases() if item["id"] == item_id)


def _clean_thresholds(value: Any) -> dict[str, dict[str, Any]]:
    supplied = value if isinstance(value, dict) else {}
    output: dict[str, dict[str, Any]] = {}
    for metric, raw in supplied.items():
        if metric not in _METRICS or not isinstance(raw, dict):
            continue
        direction = "min" if metric == "quality" else "max"
        output[metric] = {
            "direction": direction,
            "value": max(0.0, float(raw.get("value") or 0)),
            "essential": bool(raw.get("essential", metric == "quality")),
        }
    if "quality" not in output:
        output["quality"] = {"direction": "min", "value": 0.72, "essential": True}
    return output


def _public_preset(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "thresholds": _loads(row["thresholds_json"], {}),
        "protected": bool(row["protected"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_presets() -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM evaluation_presets ORDER BY protected DESC, updated_at DESC"
        ).fetchall()
    return [_public_preset(row) for row in rows]


def save_preset(payload: dict[str, Any]) -> dict[str, Any]:
    item_id = str(payload.get("id") or uuid.uuid4())
    existing = next((item for item in list_presets() if item["id"] == item_id), None)
    if existing and existing["protected"]:
        raise ValueError("O preset padrão é protegido.")
    name = str(payload.get("name") or "").strip()[:160]
    if not name:
        raise ValueError("O nome do preset é obrigatório.")
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_presets
                (id, name, thresholds_json, protected, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                thresholds_json = excluded.thresholds_json,
                updated_at = excluded.updated_at
            """,
            (
                item_id, name, _json(_clean_thresholds(payload.get("thresholds"))),
                existing["created_at"] if existing else now, now,
            ),
        )
        connection.commit()
    return next(item for item in list_presets() if item["id"] == item_id)


def _word_set(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[\wÀ-ÿ]{3,}", value)}


def _case_score(case: dict[str, Any], output: str) -> dict[str, Any]:
    lowered = output.casefold()
    required = case["essential_terms"]
    forbidden = case["forbidden_terms"]
    required_ratio = (
        sum(term.casefold() in lowered for term in required) / len(required)
        if required else 1.0
    )
    forbidden_hits = [term for term in forbidden if term.casefold() in lowered]
    good_words = _word_set(case["good_example"])
    bad_words = _word_set(case["bad_example"])
    words = _word_set(output)
    good_overlap = len(words & good_words) / max(1, len(good_words)) if good_words else 0.5
    bad_overlap = len(words & bad_words) / max(1, len(bad_words)) if bad_words else 0
    quality = max(
        0.0,
        min(1.0, 0.55 * required_ratio + 0.35 * good_overlap + 0.10 * (1 - bad_overlap)),
    )
    if forbidden_hits:
        quality *= 0.5
    return {
        "case_id": case["id"],
        "name": case["name"],
        "quality": round(quality, 4),
        "required_term_coverage": round(required_ratio, 4),
        "forbidden_hits": forbidden_hits,
        "method": "local_personal_example_heuristic_v1",
    }


def run(
    *,
    outputs: dict[str, str],
    subject_type: str,
    subject_id: str | None = None,
    preset_id: str = "essential-quality",
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preset = next((item for item in list_presets() if item["id"] == preset_id), None)
    if preset is None:
        raise KeyError(preset_id)
    cases = list_cases(enabled=True)
    if not cases:
        raise ValueError("Crie ao menos um caso de avaliação ativo.")
    results: list[dict[str, Any]] = []
    for case in cases:
        output = str(outputs.get(case["id"]) or "")
        results.append(_case_score(case, output))
    quality = statistics.fmean(item["quality"] for item in results)
    summary = {
        "quality": round(quality, 4),
        "latency_ms": max(0.0, float((metrics or {}).get("latency_ms") or 0)),
        "estimated_cost_usd": max(
            0.0, float((metrics or {}).get("estimated_cost_usd") or 0)
        ),
        "interventions": max(0, int((metrics or {}).get("interventions") or 0)),
        "cases": len(results),
    }
    gate = release_gate(summary, preset["thresholds"])
    run_id = str(uuid.uuid4())
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO evaluation_runs
                (id, subject_type, subject_id, preset_id, results_json,
                 summary_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, str(subject_type)[:80], subject_id,
                preset_id, _json(results), _json({**summary, "gate": gate}), now,
            ),
        )
        connection.commit()
    return {
        "id": run_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "preset_id": preset_id,
        "results": results,
        "summary": summary,
        "gate": gate,
        "created_at": now,
    }


def release_gate(
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for metric, rule in _clean_thresholds(thresholds).items():
        actual = float(metrics.get(metric) or 0)
        expected = float(rule["value"])
        passed = actual >= expected if rule["direction"] == "min" else actual <= expected
        if baseline and metric in baseline:
            base = float(baseline.get(metric) or 0)
            # A candidate must also avoid a >5% regression on essential metrics.
            if rule["essential"]:
                if rule["direction"] == "min":
                    passed = passed and actual >= base * 0.95
                else:
                    passed = passed and actual <= min(expected, base * 1.05)
        checks.append({
            "metric": metric,
            "actual": actual,
            "direction": rule["direction"],
            "threshold": expected,
            "essential": rule["essential"],
            "passed": passed,
        })
    essential_passed = all(
        item["passed"] for item in checks if item["essential"]
    )
    return {
        "passed": essential_passed,
        "activation_allowed": essential_passed,
        "checks": checks,
        "reason": (
            "Todos os critérios essenciais foram atendidos."
            if essential_passed
            else "A ativação foi bloqueada por regressão em critério essencial."
        ),
    }


def list_runs(*, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM evaluation_runs ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "subject_type": row["subject_type"],
            "subject_id": row["subject_id"],
            "preset_id": row["preset_id"],
            "results": _loads(row["results_json"], []),
            "summary": _loads(row["summary_json"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, _connect() as connection:
        connection.executescript(_SCHEMA)
        now = time.time()
        connection.execute(
            """
            INSERT OR IGNORE INTO evaluation_presets
                (id, name, thresholds_json, protected, created_at, updated_at)
            VALUES ('essential-quality', 'Critérios essenciais', ?, 1, ?, ?)
            """,
            (
                _json({
                    "quality": {"direction": "min", "value": 0.72, "essential": True},
                    "interventions": {"direction": "max", "value": 3, "essential": False},
                }),
                now,
                now,
            ),
        )
        connection.commit()


_init_db()
