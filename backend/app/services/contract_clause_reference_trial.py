"""Registro para ensayos de interpretación que reutilizan evidencia local."""

from collections.abc import Callable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from app.services.contract_clause_llm import ClauseModel
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_clause_v7 import V7TrialResult
from app.services.contract_clause_windows import write_json_atomically
from app.services.contract_text_extraction import ContractText


def execute_reference_trial(
    extracted: ContractText, model: ClauseModel, result_path: Path, *,
    metadata: dict[str, Any], evaluate: Callable[..., V7TrialResult],
) -> dict[str, Any]:
    if result_path.exists():
        raise TrialAlreadyRecorded("Ya existe evidencia de esta corrida; no se repite.")
    base = {
        **metadata, "started_at": datetime.now(timezone.utc).isoformat(),
        "authorized_adapter_invocations": 1, "automatic_retries_setting": 1,
        "http_attempts_verified": False,
        "pages": [{"page": p.page, "method": p.method, "readable": p.readable} for p in extracted.pages],
    }
    started = False

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
        trial = evaluate(extracted, model, before_invoke=mark_started)
    except Exception as error:
        if started:
            detail = {"type": type(error).__name__}
            status = getattr(error, "status_code", getattr(error, "code", None))
            if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
                detail["http_status"] = status
            write_json_atomically(result_path, {
                **base, "state": "failed", "finished_at": datetime.now(timezone.utc).isoformat(),
                "adapter_invocations": 1, "error": detail,
            })
        raise
    result = {
        **base, "state": "completed", "finished_at": datetime.now(timezone.utc).isoformat(),
        "adapter_invocations": 1, "model_proposals": len(trial.batch.clausulas),
        "proposals": [c.model_dump(mode="json") for c in trial.batch.clausulas],
        "valid_clauses": [c.model_dump(mode="json") for c in trial.accepted],
        "rejected_proposals": [c.model_dump(mode="json") for c in trial.rejected],
        "evidence_incidents": trial.incidents, "source_assignments": trial.assignments,
        "evidence_origin": "complete_local_segment_fragments",
        "source_preserved": trial.prepared.reconstructed_pages() == {p.page: p.text for p in extracted.pages},
    }
    write_json_atomically(result_path, result)
    return result
