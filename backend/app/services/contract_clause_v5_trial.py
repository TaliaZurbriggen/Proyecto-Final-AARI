"""Checkpoint recuperable para una sola invocación experimental v5."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from app.services.contract_clause_llm import ClauseModel
from app.services.contract_clause_v5 import evaluate_v5_with_model
from app.services.contract_clause_windows import write_json_atomically
from app.services.contract_text_extraction import ContractText


class TrialAlreadyRecorded(ValueError):
    """Hay evidencia de una ejecución previa; nunca repetirla automáticamente."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(error: Exception) -> dict[str, Any]:
    detail: dict[str, Any] = {"type": type(error).__name__}
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        status = getattr(error, "code", None)
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        detail["http_status"] = status
    return detail


def execute_v5_trial(
    extracted: ContractText,
    model: ClauseModel,
    result_path: Path,
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Guarda el inicio antes del modelo y nunca sobrescribe un intento anterior."""

    if result_path.exists():
        raise TrialAlreadyRecorded("Ya existe evidencia de esta corrida; no se repite.")
    started_at = _now()
    started = False
    base = {
        **metadata,
        "started_at": started_at,
        "authorized_adapter_invocations": 1,
        "automatic_retries_setting": 1,
        "http_attempts_verified": False,
        "pages": [
            {"page": page.page, "method": page.method, "readable": page.readable}
            for page in extracted.pages
        ],
    }

    def mark_started() -> None:
        nonlocal started
        result_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with result_path.open("x", encoding="utf-8") as stream:
                json.dump({**base, "state": "started"}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise TrialAlreadyRecorded("Ya existe evidencia de esta corrida; no se repite.") from error
        started = True

    try:
        trial = evaluate_v5_with_model(extracted, model, before_invoke=mark_started)
    except Exception as error:
        if started:
            write_json_atomically(result_path, {
                **base,
                "state": "failed",
                "finished_at": _now(),
                "adapter_invocations": 1,
                "error": _safe_error(error),
            })
        raise

    result = {
        **base,
        "state": "completed",
        "finished_at": _now(),
        "adapter_invocations": 1,
        "model_proposals": len(trial.batch.clausulas),
        "proposals": [item.model_dump(mode="json") for item in trial.batch.clausulas],
        "valid_clauses": [item.model_dump(mode="json") for item in trial.accepted],
        "rejected_proposals": [item.model_dump(mode="json") for item in trial.rejected],
        "evidence_incidents": trial.incidents,
        "source_preserved": trial.prepared.reconstructed_pages() == {
            page.page: page.text for page in extracted.pages
        },
    }
    write_json_atomically(result_path, result)
    return result
