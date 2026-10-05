"""Ensayo v6 aislado: citas completas y alcance incierto, sin cambiar producción."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

from app.schemas.clausulas_contrato import ExtractedClause, ExtractedClauseBatch, RejectedClause
from app.services.contract_clause_llm import ClauseModel, parse_batch
from app.services.contract_clause_segments import validate_clause_segments
from app.services.contract_clause_v5 import SegmentedContractInput, build_segmented_input
from app.services.contract_text_extraction import ContractText, minimize_personal_data


PROMPT_VERSION = "v6-experimental"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "prompt_extraccion_clausulas_v6.md"
_SOURCE_PHRASE_WORDS = 5


@dataclass(frozen=True)
class V6TrialResult:
    batch: ExtractedClauseBatch
    accepted: list[ExtractedClause]
    rejected: list[RejectedClause]
    incidents: list[str]
    prepared: SegmentedContractInput


def build_v6_prompt(prepared: SegmentedContractInput) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    placeholder = "{{TEXTO_CONTRATO}}"
    if template.count(placeholder) != 1:
        raise ValueError("El prompt experimental v6 no tiene un marcador único.")
    return template.replace(placeholder, minimize_personal_data(prepared.model_text))


def _words(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return re.findall(r"[a-z0-9]+", folded)


def _source_phrases_not_cited(clause: ExtractedClause, source: str) -> bool:
    """Detecta frases de la fuente reutilizadas en la interpretación pero no citadas.

    Es un control conservador de cobertura literal, no una prueba semántica.
    """

    source_words = _words(source)
    cited_words = _words(" ".join(item.texto for item in clause.evidencias))
    source_phrases = {
        tuple(source_words[index:index + _SOURCE_PHRASE_WORDS])
        for index in range(len(source_words) - _SOURCE_PHRASE_WORDS + 1)
    }
    cited_phrases = {
        tuple(cited_words[index:index + _SOURCE_PHRASE_WORDS])
        for index in range(len(cited_words) - _SOURCE_PHRASE_WORDS + 1)
    }
    for field in (clause.resumen, clause.condiciones or ""):
        words = _words(field)
        for index in range(len(words) - _SOURCE_PHRASE_WORDS + 1):
            phrase = tuple(words[index:index + _SOURCE_PHRASE_WORDS])
            if phrase in source_phrases and phrase not in cited_phrases:
                return True
    return False


def validate_v6_batch(
    batch: ExtractedClauseBatch,
    pages: dict[int, str],
) -> tuple[list[ExtractedClause], list[RejectedClause], list[str]]:
    """Mantiene el anclaje v5 y rechaza texto fuente interpretado sin cita."""

    valid, rejected, incidents = validate_clause_segments(batch, pages)
    already_rejected = {item.ordinal for item in rejected}
    accepted: list[ExtractedClause] = []
    anchored = iter(valid)
    source = "\n".join(pages[page] for page in sorted(pages))
    for ordinal, _original in enumerate(batch.clausulas, start=1):
        if ordinal in already_rejected:
            continue
        clause = next(anchored)
        if any("..." in item.texto or "…" in item.texto for item in _original.evidencias):
            reason = "la cita contiene puntos suspensivos y debe reemplazarse por fragmentos literales separados."
        elif _source_phrases_not_cited(clause, source):
            reason = (
                "el resumen o las condiciones reutilizan texto de la fuente "
                "que no figura en las evidencias citadas."
            )
        else:
            accepted.append(clause)
            continue
        rejected.append(RejectedClause(
            ordinal=ordinal, propuesta=clause, motivo=reason,
            evidencias_invalidas=[],
        ))
        incidents.append(f"La propuesta {ordinal} requiere revisión de cobertura: {reason}")
    rejected.sort(key=lambda item: item.ordinal)
    return accepted, rejected, incidents


def evaluate_v6_with_model(
    extracted: ContractText,
    model: ClauseModel,
    *,
    before_invoke: Callable[[], None] | None = None,
) -> V6TrialResult:
    """Prepara la entrada y llama una vez al modelo inyectado si se autorizara."""

    prepared = build_segmented_input(extracted)
    prompt = build_v6_prompt(prepared)
    if before_invoke is not None:
        before_invoke()
    batch = parse_batch(model.invoke(prompt))
    accepted, rejected, incidents = validate_v6_batch(
        batch, {page.page: page.text for page in extracted.pages}
    )
    return V6TrialResult(batch, accepted, rejected, incidents, prepared)
