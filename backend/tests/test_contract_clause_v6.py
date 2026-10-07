"""La v6 experimental bloquea citas incompletas sin llamar a Gemini."""

from app.schemas.clausulas_contrato import ExtractedClauseBatch
from app.services.contract_clause_v6 import (
    PROMPT_VERSION,
    build_v6_prompt,
    evaluate_v6_with_model,
    validate_v6_batch,
)
from app.services.contract_clause_v5 import build_segmented_input
from app.services.contract_text_extraction import ContractText, PageText


SOURCE = (
    "PRIMERA: El administrador paga la reparación de la caldera, "
    "salvo cuando el daño resulte del uso indebido del ocupante."
)
PREFIX = "PRIMERA: El administrador paga la reparación de la caldera"
SUFFIX = "salvo cuando el daño resulte del uso indebido del ocupante"


def _clause(evidence: list[str], *, conditions: str | None = SUFFIX) -> dict:
    return {
        "numero": "PRIMERA", "titulo": None,
        "evidencias": [{"pagina": 1, "texto": item} for item in evidence],
        "resumen": "El administrador paga la reparación de la caldera.",
        "categoria": "reparacion", "responsable": "condicional",
        "uso_clasificador": "operativa", "condiciones": conditions,
        "referencias": [], "confianza": 0.7,
    }


def _batch(evidence: list[str], *, conditions: str | None = SUFFIX):
    return ExtractedClauseBatch.model_validate({
        "clausulas": [_clause(evidence, conditions=conditions)]
    })


def test_v6_rejects_condition_present_in_source_but_missing_from_quote():
    accepted, rejected, incidents = validate_v6_batch(_batch([PREFIX]), {1: SOURCE})

    assert accepted == []
    assert len(rejected) == 1
    assert rejected[0].ordinal == 1
    assert "no figura en las evidencias" in rejected[0].motivo
    assert len(incidents) == 1


def test_v6_accepts_separate_literal_quotes_for_actor_and_condition():
    accepted, rejected, _ = validate_v6_batch(_batch([PREFIX, SUFFIX]), {1: SOURCE})

    assert len(accepted) == 1
    assert rejected == []
    assert accepted[0].evidencias[0].texto == PREFIX
    assert accepted[0].evidencias[1].texto == SUFFIX


def test_v6_never_repairs_an_ellipsis_or_a_quote_from_neighboring_clause():
    source = SOURCE + "\nSEGUNDA: El ocupante avisa todo desperfecto de inmediato."
    batch = ExtractedClauseBatch.model_validate({"clausulas": [
        _clause(["PRIMERA: El administrador paga" + " ... " + SUFFIX]),
        _clause(["El ocupante avisa todo desperfecto de inmediato"]),
    ]})

    accepted, rejected, _ = validate_v6_batch(batch, {1: source})

    assert accepted == []
    assert [item.ordinal for item in rejected] == [1, 2]
    assert "puntos suspensivos" in rejected[0].motivo or "cambia caracteres" in rejected[0].motivo
    assert "única cláusula" in rejected[1].motivo


def test_v6_rejects_ellipsis_even_if_normalized_analyzer_could_anchor_it():
    batch = _batch([PREFIX + " ... " + SUFFIX])

    accepted, rejected, _ = validate_v6_batch(batch, {1: SOURCE})

    assert accepted == []
    assert len(rejected) == 1
    assert "puntos suspensivos" in rejected[0].motivo


def test_v6_prompt_preserves_source_and_masks_identifiers():
    document = ContractText([PageText(
        1, SOURCE + " DNI 00000000", "digital", True
    )], True)
    prepared = build_segmented_input(document)
    prompt = build_v6_prompt(prepared)

    assert PROMPT_VERSION == "v6-experimental"
    assert prepared.reconstructed_pages()[1] == document.pages[0].text
    assert "00000000" not in prompt
    assert "[IDENTIFICADOR OMITIDO]" in prompt
    assert "{{TEXTO_CONTRATO}}" not in prompt
    assert "nunca las unas con `...`" in prompt


def test_v6_uses_injected_model_once_and_keeps_production_separate():
    document = ContractText([PageText(1, SOURCE, "digital", True)], True)

    class FakeModel:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            assert "[TRAMO 1 | CLÁUSULA 1]" in prompt
            return {"clausulas": [_clause([PREFIX, SUFFIX])]}

    model = FakeModel()
    result = evaluate_v6_with_model(document, model)

    assert model.calls == 1
    assert len(result.accepted) == 1
    assert result.rejected == []
