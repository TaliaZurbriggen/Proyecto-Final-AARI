"""Ensayo v7: el modelo interpreta tramos y la evidencia procede de la fuente local."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.schemas.clausulas_contrato import (
    ClauseCategory, ClauseResponsible, ClauseUsage, ExtractedClause,
)
from app.services.contract_clause_llm import ClauseModel
from app.services.contract_clause_v5 import SegmentedContractInput, build_segmented_input
from app.services.contract_text_extraction import ContractText, minimize_personal_data


PROMPT_VERSION = "v7-experimental"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "prompt_extraccion_clausulas_v7.md"


class SourceClauseProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tramo_id: int = Field(ge=1, strict=True)
    titulo: str | None = Field(default=None, max_length=200)
    resumen: str = Field(min_length=1, max_length=1200)
    categoria: ClauseCategory
    responsable: ClauseResponsible
    uso_clasificador: ClauseUsage
    condiciones: str | None = Field(default=None, max_length=1600)
    referencias: list[str] = Field(default_factory=list, max_length=20)
    confianza: float = Field(ge=0, le=1)


class SourceClauseBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clausulas: list[SourceClauseProposal] = Field(default_factory=list, max_length=120)


class SourceProposalRejection(BaseModel):
    ordinal: int
    propuesta: SourceClauseProposal
    motivo: str


@dataclass(frozen=True)
class V7TrialResult:
    batch: SourceClauseBatch
    accepted: list[ExtractedClause]
    rejected: list[SourceProposalRejection]
    incidents: list[str]
    prepared: SegmentedContractInput
    assignments: list[dict[str, object]]


def build_v7_prompt(prepared: SegmentedContractInput) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    placeholder = "{{TEXTO_CONTRATO}}"
    if template.count(placeholder) != 1:
        raise ValueError("El prompt v7 requiere un marcador único de texto.")
    return template.replace(placeholder, minimize_personal_data(prepared.model_text))


def get_v7_model(model_name: str) -> ClauseModel:
    if os.getenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "false").lower() not in {"true", "1", "yes"}:
        raise RuntimeError("El análisis externo está deshabilitado.")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("El análisis con Gemini no está configurado.")
    model = ChatGoogleGenerativeAI(
        model=model_name, google_api_key=key, max_retries=1,
    )
    return model.with_structured_output(SourceClauseBatch, method="function_calling")


def materialize_v7_batch(
    batch: SourceClauseBatch,
    prepared: SegmentedContractInput,
) -> tuple[list[ExtractedClause], list[SourceProposalRejection], list[str], list[dict[str, object]]]:
    """Adjunta todos los fragmentos de un tramo, sin aceptar texto o páginas del modelo."""

    catalog = {}
    for block in prepared.blocks:
        if block.segment_index is not None:
            catalog.setdefault(block.segment_index, []).append(block)
    accepted = []
    rejected = []
    incidents = []
    assignments = []
    for ordinal, proposal in enumerate(batch.clausulas, start=1):
        blocks = catalog.get(proposal.tramo_id)
        reason = None
        if blocks is None:
            reason = "el tramo indicado no existe en la fuente local."
        elif blocks[0].label is None:
            reason = "el encabezado del tramo no se reconoce; requiere revisión de segmentación."
        elif len(blocks) > 20 or len("\n\n".join(block.text.strip() for block in blocks)) > 8000:
            reason = "el tramo excede los límites de evidencia; no se truncó su texto."
        else:
            payload = proposal.model_dump(exclude={"tramo_id"})
            payload["numero"] = blocks[0].label
            payload["evidencias"] = [
                {"pagina": block.page, "texto": block.text}
                for block in blocks
            ]
            try:
                clause = ExtractedClause.model_validate(payload)
            except ValidationError:
                reason = "la propuesta no pudo materializarse con evidencia completa."
            else:
                accepted.append(clause)
                assignments.append({
                    "proposal_ordinal": ordinal, "tramo_id": proposal.tramo_id,
                    "numero": clause.numero, "paginas": clause.paginas,
                })
        if reason:
            rejected.append(SourceProposalRejection(ordinal=ordinal, propuesta=proposal, motivo=reason))
            incidents.append(f"La propuesta {ordinal} requiere revisión: {reason}")
    return accepted, rejected, incidents, assignments


def evaluate_v7_with_model(
    extracted: ContractText,
    model: ClauseModel,
    *,
    before_invoke: Callable[[], None] | None = None,
) -> V7TrialResult:
    prepared = build_segmented_input(extracted)
    if not any(block.segment_index is not None for block in prepared.blocks):
        raise ValueError("No hay tramos identificados para interpretar.")
    prompt = build_v7_prompt(prepared)
    if before_invoke is not None:
        before_invoke()
    output = model.invoke(prompt)
    batch = output if isinstance(output, SourceClauseBatch) else SourceClauseBatch.model_validate(output)
    accepted, rejected, incidents, assignments = materialize_v7_batch(batch, prepared)
    return V7TrialResult(batch, accepted, rejected, incidents, prepared, assignments)
