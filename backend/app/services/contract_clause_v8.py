"""Refinamiento semántico v8 sobre la misma evidencia local congelada de v7."""

from collections.abc import Callable
from pathlib import Path

from app.services.contract_clause_llm import ClauseModel
from app.services.contract_clause_v5 import SegmentedContractInput, build_segmented_input
from app.services.contract_clause_v7 import SourceClauseBatch, V7TrialResult, materialize_v7_batch
from app.services.contract_text_extraction import ContractText, minimize_personal_data


PROMPT_VERSION = "v8-experimental"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "prompt_extraccion_clausulas_v8.md"


def build_v8_prompt(prepared: SegmentedContractInput) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    placeholder = "{{TEXTO_CONTRATO}}"
    if template.count(placeholder) != 1:
        raise ValueError("El prompt v8 requiere un marcador único de texto.")
    return template.replace(placeholder, minimize_personal_data(prepared.model_text))


def evaluate_v8_with_model(
    extracted: ContractText,
    model: ClauseModel,
    *,
    before_invoke: Callable[[], None] | None = None,
) -> V7TrialResult:
    prepared = build_segmented_input(extracted)
    if not any(block.segment_index is not None for block in prepared.blocks):
        raise ValueError("No hay tramos identificados para interpretar.")
    prompt = build_v8_prompt(prepared)
    if before_invoke is not None:
        before_invoke()
    output = model.invoke(prompt)
    batch = output if isinstance(output, SourceClauseBatch) else SourceClauseBatch.model_validate(output)
    accepted, rejected, incidents, assignments = materialize_v7_batch(batch, prepared)
    return V7TrialResult(batch, accepted, rejected, incidents, prepared, assignments)
