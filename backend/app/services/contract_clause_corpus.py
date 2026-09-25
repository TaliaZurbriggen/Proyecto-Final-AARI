"""Controles reproducibles para evaluar HU30 sin ajustar el prompt al corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ContractClauseCorpusError(ValueError):
    """El corpus o una revisión no cumple las condiciones de evaluación."""


REVIEW_STATES = {"completo", "parcial", "omitido", "incorrecto"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractClauseCorpusError(f"No se pudo leer {path}.") from error
    if not isinstance(value, dict):
        raise ContractClauseCorpusError(f"{path} debe contener un objeto JSON.")
    return value


def verify_prompt_freeze(manifest: dict[str, Any], project_root: Path) -> list[dict[str, str]]:
    freeze = manifest.get("prompt_freeze") or {}
    files = freeze.get("files") or []
    if not files:
        raise ContractClauseCorpusError("El manifiesto no define archivos congelados.")

    verified = []
    for item in files:
        relative_path = item.get("path")
        expected = str(item.get("sha256", "")).lower()
        if not relative_path or len(expected) != 64:
            raise ContractClauseCorpusError("La congelación del prompt está incompleta.")
        path = project_root / relative_path
        if not path.is_file():
            raise ContractClauseCorpusError(f"Falta el archivo congelado {relative_path}.")
        actual = file_sha256(path)
        if actual != expected:
            raise ContractClauseCorpusError(
                f"El archivo congelado {relative_path} cambió: {actual}."
            )
        verified.append({"path": relative_path, "sha256": actual})
    return verified


def get_document(manifest: dict[str, Any], document_id: str) -> dict[str, Any]:
    for document in manifest.get("documents") or []:
        if document.get("id") == document_id:
            return document
    raise ContractClauseCorpusError(f"El documento {document_id} no existe en el corpus.")


def verify_document(
    document: dict[str, Any],
    project_root: Path,
    *,
    require_validated_expectations: bool = True,
) -> Path:
    if document.get("role") == "holdout":
        raise ContractClauseCorpusError(
            "Los holdouts permanecen reservados y no se ejecutan desde este corpus."
        )
    if require_validated_expectations and document.get("expectations_state") != "validated":
        raise ContractClauseCorpusError(
            f"Los resultados esperados de {document.get('id')} aún no fueron validados."
        )
    relative_path = document.get("path")
    expected = str(document.get("sha256", "")).lower()
    if not relative_path or len(expected) != 64:
        raise ContractClauseCorpusError(
            f"El documento {document.get('id')} no tiene archivo y hash verificables."
        )
    path = project_root / relative_path
    if not path.is_file():
        raise ContractClauseCorpusError(f"Falta el archivo {relative_path}.")
    actual = file_sha256(path)
    if actual != expected:
        raise ContractClauseCorpusError(
            f"El archivo {relative_path} no coincide con el hash del manifiesto."
        )
    return path


def get_expected_controls(
    controls_file: dict[str, Any],
    document_id: str,
    *,
    require_validated: bool = True,
) -> list[dict[str, Any]]:
    document = (controls_file.get("documents") or {}).get(document_id)
    if not isinstance(document, dict):
        raise ContractClauseCorpusError(
            f"No existen controles esperados para {document_id}."
        )
    if require_validated and document.get("state") != "validated":
        raise ContractClauseCorpusError(
            f"Los controles esperados de {document_id} continúan en borrador."
        )
    controls = document.get("controls")
    if not isinstance(controls, list) or not controls:
        raise ContractClauseCorpusError(
            f"{document_id} debe tener al menos un control esperado."
        )
    return controls


def calculate_review_metrics(
    controls: list[dict[str, Any]],
    review: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    """Calcula cobertura sin quitar omitidos o inválidos del denominador."""

    expected = {item.get("id"): item for item in controls}
    if not expected or None in expected or len(expected) != len(controls):
        raise ContractClauseCorpusError("Los controles esperados deben tener IDs únicos.")

    observed_items = review.get("controls") or []
    observed: dict[str, dict[str, Any]] = {}
    for item in observed_items:
        control_id = item.get("id")
        state = item.get("state")
        if control_id not in expected:
            raise ContractClauseCorpusError(f"La revisión contiene el control desconocido {control_id}.")
        if control_id in observed:
            raise ContractClauseCorpusError(f"La revisión repite el control {control_id}.")
        if state not in REVIEW_STATES:
            raise ContractClauseCorpusError(f"El estado de {control_id} no es válido.")
        observed[control_id] = item

    missing = sorted(set(expected) - set(observed))
    if missing:
        raise ContractClauseCorpusError(
            "La revisión debe incluir todos los controles: " + ", ".join(missing)
        )

    total = len(expected)
    complete = sum(item["state"] == "completo" for item in observed.values())
    partial = sum(item["state"] == "parcial" for item in observed.values())
    incorrect = sum(item["state"] == "incorrecto" for item in observed.values())
    omitted = sum(item["state"] == "omitido" for item in observed.values())
    located = complete + partial
    critical_ids = {key for key, item in expected.items() if item.get("critical") is True}
    critical_complete = sum(observed[key]["state"] == "completo" for key in critical_ids)
    critical_located = sum(
        observed[key]["state"] in {"completo", "parcial"} for key in critical_ids
    )
    accepted_hallucinations = review.get("accepted_hallucinations")
    if not isinstance(accepted_hallucinations, int) or accepted_hallucinations < 0:
        raise ContractClauseCorpusError(
            "accepted_hallucinations debe ser un entero mayor o igual que cero."
        )

    general_coverage = complete / total
    critical_recall = critical_complete / len(critical_ids) if critical_ids else 1.0
    minimum_general = float(thresholds["minimum_general_coverage"])
    minimum_critical = float(thresholds["minimum_critical_recall"])
    maximum_hallucinations = int(thresholds["maximum_accepted_hallucinations"])
    passed = (
        general_coverage >= minimum_general
        and critical_recall >= minimum_critical
        and accepted_hallucinations <= maximum_hallucinations
    )
    return {
        "controls_total": total,
        "controls_complete": complete,
        "controls_partial": partial,
        "controls_incorrect": incorrect,
        "controls_omitted": omitted,
        "general_coverage": general_coverage,
        "controls_located": located,
        "content_recall": located / total,
        "critical_controls_total": len(critical_ids),
        "critical_controls_complete": critical_complete,
        "critical_recall": critical_recall,
        "critical_controls_located": critical_located,
        "critical_content_recall": (
            critical_located / len(critical_ids) if critical_ids else 1.0
        ),
        "accepted_hallucinations": accepted_hallucinations,
        "passed": passed,
    }
