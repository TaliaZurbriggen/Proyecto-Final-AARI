"""Anclaje conservador de evidencia del modelo al texto exacto del PDF."""

from __future__ import annotations

import unicodedata

from app.schemas.clausulas_contrato import (
    ClauseEvidence,
    ExtractedClause,
    ExtractedClauseBatch,
    RejectedClause,
)


MIN_COMPACT_EVIDENCE_CHARACTERS = 24


def _compact_with_positions(text: str) -> tuple[str, list[int]]:
    """Quita formato y conserva la posición de cada carácter alfanumérico."""

    compact: list[str] = []
    positions: list[int] = []
    for original_index, character in enumerate(text or ""):
        if character == "\u00ad":
            continue
        normalized = unicodedata.normalize("NFKC", character).casefold()
        for item in normalized:
            if item.isalnum():
                compact.append(item)
                positions.append(original_index)
    return "".join(compact), positions


def anchor_evidence(evidence: ClauseEvidence, page_text: str) -> tuple[ClauseEvidence | None, str | None]:
    """Devuelve el fragmento exacto de origen si existe una coincidencia única."""

    if not page_text:
        return None, f"la página {evidence.pagina} no está disponible"

    compact_evidence, _ = _compact_with_positions(evidence.texto)
    if len(compact_evidence) < MIN_COMPACT_EVIDENCE_CHARACTERS:
        return None, (
            f"el fragmento de la página {evidence.pagina} es demasiado breve "
            "para anclarlo con seguridad"
        )

    compact_page, positions = _compact_with_positions(page_text)
    occurrences: list[int] = []
    offset = 0
    while True:
        index = compact_page.find(compact_evidence, offset)
        if index < 0:
            break
        occurrences.append(index)
        offset = index + 1

    if not occurrences:
        return None, (
            f"el fragmento de la página {evidence.pagina} cambia caracteres "
            "del texto de origen"
        )
    if len(occurrences) > 1:
        return None, (
            f"el fragmento de la página {evidence.pagina} aparece más de una vez"
        )

    compact_start = occurrences[0]
    compact_end = compact_start + len(compact_evidence) - 1
    source_start = positions[compact_start]
    source_end = positions[compact_end] + 1
    source_text = page_text[source_start:source_end].strip()
    return ClauseEvidence(pagina=evidence.pagina, texto=source_text), None


def validate_and_anchor_evidence(
    batch: ExtractedClauseBatch,
    pages: dict[int, str],
) -> tuple[list[ExtractedClause], list[RejectedClause], list[str]]:
    """Valida cada cita y reemplaza la salida del modelo por texto del PDF."""

    valid: list[ExtractedClause] = []
    rejected: list[RejectedClause] = []
    incidents: list[str] = []
    for index, clause in enumerate(batch.clausulas, start=1):
        anchored: list[ClauseEvidence] = []
        invalid: list[ClauseEvidence] = []
        reasons: list[str] = []
        for evidence in clause.evidencias:
            located, reason = anchor_evidence(evidence, pages.get(evidence.pagina, ""))
            if located is None:
                invalid.append(evidence)
                reasons.append(reason or "la evidencia no pudo anclarse")
            else:
                anchored.append(located)

        if invalid:
            reason = "; ".join(dict.fromkeys(reasons)) + "."
            rejected.append(RejectedClause(
                ordinal=index,
                propuesta=clause,
                motivo=reason,
                evidencias_invalidas=invalid,
            ))
            incidents.append(f"La propuesta {index} requiere revisión de evidencia: {reason}")
            continue

        payload = clause.model_dump(mode="python")
        payload["evidencias"] = [item.model_dump(mode="python") for item in anchored]
        valid.append(ExtractedClause.model_validate(payload))
    return valid, rejected, incidents
