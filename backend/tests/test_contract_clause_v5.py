"""El ensayo v5 conserva el documento y sólo usa modelos inyectados."""

import pytest

from app.services.contract_clause_v5 import (
    PROMPT_VERSION,
    SegmentedInputError,
    build_segmented_input,
    build_v5_prompt,
    evaluate_v5_with_model,
)
from app.services.contract_text_extraction import ContractText, PageText


def document(first, second=None):
    pages = [PageText(1, first, "digital", True)]
    if second is not None:
        pages.append(PageText(2, second, "digital", True))
    return ContractText(pages, True)


def test_preserves_preamble_and_cross_page_clause_without_text_loss():
    first = (
        "Nota introductoria y datos generales.\n"
        "PRIMERA: El inmueble se destina exclusivamente a vivienda.\n"
        "QUINTA: El locador hará las reparaciones necesarias para mantener"
    )
    second = (
        " el edificio apto durante toda la vigencia.\n"
        "SEXTA: Los gastos comunes requieren revisión individual."
    )
    prepared = build_segmented_input(document(first, second))

    assert prepared.reconstructed_pages() == {1: first, 2: second}
    assert [block.segment_index for block in prepared.blocks] == [None, 1, 2, 2, 3]
    assert prepared.blocks[3].continuation is True
    assert "[TRAMO 2 | CLÁUSULA 5 | CONTINÚA DE LA PÁGINA ANTERIOR]" in prepared.model_text
    assert prepared.model_text.count("Nota introductoria y datos generales.") == 1
    assert prepared.model_text.count("el edificio apto durante toda la vigencia") == 1


def test_unknown_heading_keeps_source_without_guessing_its_number():
    source = (
        "ARTÍCULO QUINTO - ENTREGA: El inmueble se entrega habitable.\n"
        "ARTÍCULO XTO - REPARACIONES: El locador conserva la estructura.\n"
        "ARTÍCULO SÉPTIMO - USO: El locatario lo mantiene limpio."
    )
    prepared = build_segmented_input(document(source))

    assert prepared.reconstructed_pages() == {1: source}
    assert [block.label for block in prepared.blocks] == ["5", None, "7"]
    assert "[TRAMO 2 | ENCABEZADO NO RECONOCIDO]" in prepared.model_text


def test_text_without_detectable_clause_is_kept_as_unassigned():
    source = "Texto legible sin un encabezado numerado de cláusula."
    prepared = build_segmented_input(document(source))

    assert prepared.reconstructed_pages() == {1: source}
    assert len(prepared.blocks) == 1
    assert prepared.blocks[0].segment_index is None


def test_incomplete_document_is_rejected_before_any_model_call():
    extracted = ContractText([
        PageText(1, "PRIMERA: El contrato comienza hoy.", "digital", True),
        PageText(2, "", "sin_lectura", False),
    ], False)

    with pytest.raises(SegmentedInputError, match="legibles"):
        build_segmented_input(extracted)


def test_v5_prompt_is_separate_and_minimizes_identifiers():
    prepared = build_segmented_input(document(
        "PRIMERA: El DNI 00000000 identifica al locatario."
    ))
    prompt = build_v5_prompt(prepared)

    assert PROMPT_VERSION == "v5-experimental"
    assert "00000000" not in prompt
    assert "[IDENTIFICADOR OMITIDO]" in prompt
    assert "{{TEXTO_CONTRATO}}" not in prompt
    assert "[TRAMO 1 | CLÁUSULA 1]" in prompt


def test_experiment_invokes_fake_once_and_keeps_neighboring_quote_rejected():
    source = (
        "SEXTA: Los gastos comunes requieren revisión individual.\n"
        "SÉPTIMA: El locatario devuelve el inmueble en buen estado."
    )

    class FakeModel:
        def __init__(self):
            self.prompts = []

        def invoke(self, prompt):
            self.prompts.append(prompt)
            return {"clausulas": [
                {
                    "numero": "SEXTA", "titulo": None,
                    "evidencias": [{
                        "pagina": 1,
                        "texto": "El locatario devuelve el inmueble en buen estado",
                    }],
                    "resumen": "El locatario devuelve el inmueble en buen estado.",
                    "categoria": "devolucion", "responsable": "inquilino",
                    "uso_clasificador": "contexto", "condiciones": None,
                    "referencias": [], "confianza": 0.5,
                },
                {
                    "numero": "SÉPTIMA", "titulo": None,
                    "evidencias": [{
                        "pagina": 1,
                        "texto": "El locatario devuelve el inmueble en buen estado",
                    }],
                    "resumen": "El locatario devuelve el inmueble en buen estado.",
                    "categoria": "devolucion", "responsable": "inquilino",
                    "uso_clasificador": "contexto", "condiciones": None,
                    "referencias": [], "confianza": 0.5,
                },
            ]}

    model = FakeModel()
    result = evaluate_v5_with_model(document(source), model)

    assert len(model.prompts) == 1
    assert len(result.batch.clausulas) == 2
    assert "[TRAMO 1 | CLÁUSULA 6]" in model.prompts[0]
    assert len(result.accepted) == 1
    assert result.accepted[0].numero == "SÉPTIMA"
    assert len(result.rejected) == 1
    assert "única cláusula" in result.rejected[0].motivo
