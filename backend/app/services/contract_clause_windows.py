"""Evaluación reanudable de contratos por ventanas de páginas contiguas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from app.schemas.clausulas_contrato import ExtractedClause, ExtractedClauseBatch, RejectedClause
from app.services.contract_clause_corpus import ContractClauseCorpusError
from app.services.contract_clause_evidence import validate_and_anchor_evidence
from app.services.contract_clause_llm import ClauseModel, build_clause_prompt, parse_batch
from app.services.contract_text_extraction import PageText, minimize_personal_data


@dataclass(frozen=True)
class ClauseWindow:
    index: int
    pages: tuple[PageText, ...]

    @property
    def page_numbers(self) -> list[int]:
        return [page.page for page in self.pages]

    @property
    def model_text(self) -> str:
        return "\n\n".join(
            f"[PÁGINA {page.page}]\n{page.text}" for page in self.pages if page.text
        )

    @property
    def page_texts(self) -> dict[int, str]:
        return {page.page: page.text for page in self.pages}


def build_clause_windows(
    pages: list[PageText], *, pages_per_window: int = 2, overlap_pages: int = 1
) -> list[ClauseWindow]:
    if pages_per_window < 1 or overlap_pages < 0 or overlap_pages >= pages_per_window:
        raise ContractClauseCorpusError("La configuración de ventanas no es válida.")
    if not pages:
        raise ContractClauseCorpusError("El documento no tiene páginas para evaluar.")
    numbers = [page.page for page in pages]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ContractClauseCorpusError("Las páginas deben estar ordenadas y ser consecutivas.")

    windows: list[ClauseWindow] = []
    start = 0
    step = pages_per_window - overlap_pages
    while True:
        selected = tuple(pages[start:start + pages_per_window])
        windows.append(ClauseWindow(index=len(windows) + 1, pages=selected))
        if start + pages_per_window >= len(pages):
            return windows
        start += step


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """Publica un checkpoint completo o no publica ninguno."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def evaluate_clause_window(
    window: ClauseWindow,
    model: ClauseModel,
    *,
    document_id: str,
    source_sha256: str,
    prompt_version: str,
    model_name: str,
    result_path: Path,
) -> dict[str, Any]:
    if result_path.exists():
        raise ContractClauseCorpusError(
            f"La ventana {window.index} ya tiene resultado; no se repite la llamada."
        )

    started = time.monotonic()
    batch = parse_batch(model.invoke(build_clause_prompt(minimize_personal_data(window.model_text))))
    valid, rejected, incidents = validate_and_anchor_evidence(batch, window.page_texts)
    result = {
        "document": document_id,
        "window_index": window.index,
        "pages": window.page_numbers,
        "source_sha256": source_sha256,
        "prompt_version": prompt_version,
        "model": model_name,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "external_calls": 1,
        "model_proposals": len(batch.clausulas),
        "valid_clauses": [item.model_dump(mode="json") for item in valid],
        "rejected_proposals": [item.model_dump(mode="json") for item in rejected],
        "evidence_incidents": incidents,
    }
    write_json_atomically(result_path, result)
    return result


def merge_clause_window_results(
    windows: list[ClauseWindow],
    results: list[dict[str, Any]],
    *,
    document_id: str,
    source_sha256: str,
    prompt_version: str,
    model_name: str,
) -> dict[str, Any]:
    if len(windows) != len(results):
        raise ContractClauseCorpusError("Faltan resultados de ventanas para consolidar.")

    valid_clauses: list[dict[str, Any]] = []
    rejected_proposals: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    duplicate_count = 0
    model_proposals = 0
    external_calls = 0
    incidents: list[dict[str, Any]] = []
    for window, result in zip(windows, results, strict=True):
        expected = {
            "document": document_id,
            "window_index": window.index,
            "pages": window.page_numbers,
            "source_sha256": source_sha256,
            "prompt_version": prompt_version,
            "model": model_name,
        }
        if any(result.get(key) != value for key, value in expected.items()):
            raise ContractClauseCorpusError(
                f"El resultado de la ventana {window.index} no coincide con el documento o la configuración."
            )
        proposals = result.get("model_proposals")
        calls = result.get("external_calls")
        valid_items = result.get("valid_clauses")
        rejected_items = result.get("rejected_proposals")
        evidence_incidents = result.get("evidence_incidents")
        if (
            not isinstance(proposals, int)
            or isinstance(proposals, bool)
            or proposals < 0
            or not isinstance(calls, int)
            or isinstance(calls, bool)
            or calls != 1
            or not isinstance(valid_items, list)
            or not isinstance(rejected_items, list)
            or not isinstance(evidence_incidents, list)
            or any(not isinstance(message, str) for message in evidence_incidents)
        ):
            raise ContractClauseCorpusError(f"El resultado de la ventana {window.index} está incompleto.")
        if proposals != len(valid_items) + len(rejected_items):
            raise ContractClauseCorpusError(f"Los conteos de la ventana {window.index} no coinciden.")
        model_proposals += proposals
        external_calls += calls

        for item in valid_items:
            try:
                clause = ExtractedClause.model_validate(item)
                batch = ExtractedClauseBatch(clausulas=[clause])
            except ValueError as error:
                raise ContractClauseCorpusError(
                    f"La ventana {window.index} contiene una cláusula inválida."
                ) from error
            anchored, invalid, _ = validate_and_anchor_evidence(batch, window.page_texts)
            if invalid or not anchored:
                raise ContractClauseCorpusError(
                    f"La ventana {window.index} contiene evidencia fuera de sus páginas."
                )
            canonical = anchored[0].model_dump(mode="json")
            identity = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
            if identity in seen:
                provenance[seen[identity]]["windows"].append(window.index)
                duplicate_count += 1
            else:
                seen[identity] = len(valid_clauses)
                valid_clauses.append(canonical)
                provenance.append({"clause_ordinal": len(valid_clauses), "windows": [window.index]})

        for item in rejected_items:
            try:
                rejected = RejectedClause.model_validate(item)
            except ValueError as error:
                raise ContractClauseCorpusError(
                    f"La ventana {window.index} contiene una propuesta rechazada inválida."
                ) from error
            rejected_proposals.append({
                "window_index": window.index,
                **rejected.model_dump(mode="json"),
            })
        incidents.extend(
            {"window_index": window.index, "message": message}
            for message in evidence_incidents
        )

    return {
        "document": document_id,
        "source_sha256": source_sha256,
        "prompt_version": prompt_version,
        "model": model_name,
        "strategy": "overlapping_page_windows",
        "windows_completed": len(windows),
        "external_calls": external_calls,
        "model_proposals": model_proposals,
        "valid_clauses": valid_clauses,
        "duplicate_proposals_removed": duplicate_count,
        "provenance": provenance,
        "rejected_proposals": rejected_proposals,
        "evidence_incidents": incidents,
        "human_review_required": True,
    }
