"""Ensayo aislado de extracción por tramos; producción conserva el prompt v4."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.schemas.clausulas_contrato import ExtractedClause, ExtractedClauseBatch, RejectedClause
from app.services.contract_clause_llm import ClauseModel, parse_batch
from app.services.contract_clause_segments import build_clause_segments, validate_clause_segments
from app.services.contract_text_extraction import ContractText, PageText, minimize_personal_data


PROMPT_VERSION = "v5-experimental"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "prompt_extraccion_clausulas_v5.md"


class SegmentedInputError(ValueError):
    """El documento no puede prepararse sin perder su procedencia o contenido."""


@dataclass(frozen=True)
class SourceBlock:
    page: int
    text: str
    segment_index: int | None
    label: str | None = None
    kind: str | None = None
    continuation: bool = False

    @property
    def marker(self) -> str:
        if self.segment_index is None:
            return "[TEXTO SIN TRAMO IDENTIFICADO]"
        if self.label is None:
            identity = "ENCABEZADO NO RECONOCIDO"
        else:
            kind = {"articulo": "ARTÍCULO", "clausula": "CLÁUSULA"}.get(
                self.kind, "APARTADO"
            )
            identity = f"{kind} {self.label}"
        continuation = " | CONTINÚA DE LA PÁGINA ANTERIOR" if self.continuation else ""
        return f"[TRAMO {self.segment_index} | {identity}{continuation}]"


@dataclass(frozen=True)
class SegmentedContractInput:
    pages: tuple[PageText, ...]
    blocks: tuple[SourceBlock, ...]

    @property
    def model_text(self) -> str:
        sections = []
        for page in self.pages:
            lines = [f"[PÁGINA {page.page}]"]
            for block in self.blocks:
                if block.page == page.page:
                    lines.extend((block.marker, block.text))
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def reconstructed_pages(self) -> dict[int, str]:
        return {
            page.page: "".join(block.text for block in self.blocks if block.page == page.page)
            for page in self.pages
        }


@dataclass(frozen=True)
class V5TrialResult:
    batch: ExtractedClauseBatch
    accepted: list[ExtractedClause]
    rejected: list[RejectedClause]
    incidents: list[str]
    prepared: SegmentedContractInput


def build_segmented_input(extracted: ContractText) -> SegmentedContractInput:
    """Anota tramos sobre el texto original, conservando también el preámbulo."""

    pages = tuple(extracted.pages)
    numbers = [page.page for page in pages]
    if not pages or numbers != list(range(1, len(pages) + 1)):
        raise SegmentedInputError("Las páginas deben estar completas y en orden.")
    if not extracted.complete or any(not page.readable or not page.text for page in pages):
        raise SegmentedInputError("La entrada v5 requiere todas las páginas legibles.")

    segments = build_clause_segments({page.page: page.text for page in pages})
    blocks: list[SourceBlock] = []
    for page in pages:
        cursor = 0
        for index, segment in enumerate(segments, start=1):
            for fragment in segment.fragments:
                if fragment.page != page.page:
                    continue
                position = page.text.find(fragment.text, cursor)
                if position < 0:
                    raise SegmentedInputError(
                        f"No se pudo reconstruir la página {page.page} sin cambiar su texto."
                    )
                if position > cursor:
                    blocks.append(SourceBlock(page.page, page.text[cursor:position], None))
                blocks.append(SourceBlock(
                    page=page.page,
                    text=fragment.text,
                    segment_index=index,
                    label=segment.label,
                    kind=segment.kind,
                    continuation=page.page != segment.fragments[0].page,
                ))
                cursor = position + len(fragment.text)
        if cursor < len(page.text):
            blocks.append(SourceBlock(page.page, page.text[cursor:], None))

    prepared = SegmentedContractInput(pages, tuple(blocks))
    if prepared.reconstructed_pages() != {page.page: page.text for page in pages}:
        raise SegmentedInputError("La entrada v5 no conservó todo el texto original.")
    return prepared


def build_v5_prompt(prepared: SegmentedContractInput) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    placeholder = "{{TEXTO_CONTRATO}}"
    if template.count(placeholder) != 1:
        raise SegmentedInputError("El prompt experimental no tiene un marcador único.")
    return template.replace(placeholder, minimize_personal_data(prepared.model_text))


def evaluate_v5_with_model(
    extracted: ContractText,
    model: ClauseModel,
    *,
    before_invoke: Callable[[], None] | None = None,
) -> V5TrialResult:
    """Prepara todo antes de invocar una vez el modelo autorizado."""

    prepared = build_segmented_input(extracted)
    prompt = build_v5_prompt(prepared)
    if before_invoke is not None:
        before_invoke()
    batch = parse_batch(model.invoke(prompt))
    accepted, rejected, incidents = validate_clause_segments(
        batch, {page.page: page.text for page in extracted.pages}
    )
    return V5TrialResult(batch, accepted, rejected, incidents, prepared)
