"""La evidencia v7 pertenece al tramo local, no al texto o página del modelo."""

import json

import pytest
from pydantic import ValidationError

from app.services.contract_clause_v5 import SegmentedInputError, build_segmented_input
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_clause_v7 import (
    SourceClauseBatch, build_v7_prompt, evaluate_v7_with_model, materialize_v7_batch,
)
from app.services.contract_clause_v7_trial import execute_v7_trial
from app.services.contract_text_extraction import ContractText, PageText


def document(*texts):
    return ContractText([PageText(i, text, "digital", True) for i, text in enumerate(texts, 1)], True)


def proposal(source_id=1):
    return {
        "tramo_id": source_id, "titulo": "Conservación",
        "resumen": "El locador repara el inmueble durante la vigencia.",
        "categoria": "reparacion", "responsable": "propietario",
        "uso_clasificador": "operativa", "condiciones": None,
        "referencias": [], "confianza": 0.8,
    }


def test_source_evidence_includes_whole_clause_and_cross_page_exception():
    first = "QUINTA: El locador conserva el edificio durante"
    continuation = "la vigencia, salvo daños del ocupante.\n"
    prepared = build_segmented_input(document(first, continuation + "SEXTA: El ocupante avisa los daños."))
    batch = SourceClauseBatch.model_validate({"clausulas": [proposal()]})

    accepted, rejected, _, assignments = materialize_v7_batch(batch, prepared)

    assert rejected == []
    assert accepted[0].numero == "5"
    assert accepted[0].paginas == [1, 2]
    assert accepted[0].evidencias[0].texto == first
    assert accepted[0].evidencias[1].texto == continuation.strip()
    assert "salvo daños" in accepted[0].texto_original
    assert "SEXTA" not in accepted[0].texto_original
    assert assignments[0]["tramo_id"] == 1


def test_model_cannot_supply_or_override_source_text_number_or_page():
    for forbidden in ("numero", "paginas", "evidencias", "texto_original"):
        with pytest.raises(ValidationError):
            SourceClauseBatch.model_validate({"clausulas": [{**proposal(), forbidden: "inventado"}]})


def test_nonexistent_and_unreadable_headings_are_rejected_without_guessing():
    prepared = build_segmented_input(document("ARTÍCULO XTO - DAÑOS: Se reparan los daños del edificio."))
    batch = SourceClauseBatch.model_validate({"clausulas": [proposal(99), proposal(1)]})

    accepted, rejected, _, assignments = materialize_v7_batch(batch, prepared)

    assert accepted == [] and assignments == []
    assert [item.ordinal for item in rejected] == [1, 2]
    assert "no existe" in rejected[0].motivo
    assert "no se reconoce" in rejected[1].motivo


def test_repeated_clause_labels_are_distinguished_by_source_id():
    prepared = build_segmented_input(document(
        "PRIMERA: El locador repara el techo.\nPRIMERA: El ocupante limpia el patio."
    ))
    batch = SourceClauseBatch.model_validate({"clausulas": [proposal(2)]})
    accepted, rejected, _, _ = materialize_v7_batch(batch, prepared)
    assert rejected == []
    assert "limpia el patio" in accepted[0].texto_original
    assert "repara el techo" not in accepted[0].texto_original


def test_oversized_source_is_rejected_instead_of_truncated():
    prepared = build_segmented_input(document("PRIMERA: " + "contenido " * 900))
    batch = SourceClauseBatch.model_validate({"clausulas": [proposal()]})
    accepted, rejected, _, _ = materialize_v7_batch(batch, prepared)
    assert accepted == []
    assert "no se truncó" in rejected[0].motivo


def test_prompt_masks_identifiers_and_one_source_may_have_multiple_rules():
    prepared = build_segmented_input(document("PRIMERA: DNI 00000000. El locador repara el edificio."))
    prompt = build_v7_prompt(prepared)
    assert "00000000" not in prompt
    assert "[IDENTIFICADOR OMITIDO]" in prompt
    batch = SourceClauseBatch.model_validate({"clausulas": [proposal(), proposal()]})
    accepted, rejected, _, assignments = materialize_v7_batch(batch, prepared)
    assert len(accepted) == len(assignments) == 2
    assert rejected == []


class FakeModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, _prompt):
        self.calls += 1
        return {"clausulas": [proposal()]}


def test_checkpoint_keeps_model_proposal_and_locally_materialized_evidence(tmp_path):
    output = tmp_path / "result.json"
    model = FakeModel()
    extracted = document("PRIMERA: El locador conserva el edificio.")
    result = execute_v7_trial(extracted, model, output, metadata={})
    assert result["state"] == "completed"
    assert "evidencias" not in result["proposals"][0]
    assert result["valid_clauses"][0]["evidencias"][0]["pagina"] == 1
    assert result["source_assignments"][0]["proposal_ordinal"] == 1
    with pytest.raises(TrialAlreadyRecorded):
        execute_v7_trial(extracted, model, output, metadata={})
    assert model.calls == 1


def test_failed_trial_has_safe_status_and_never_retries(tmp_path):
    class ServiceError(Exception):
        code = 503

    class BrokenModel(FakeModel):
        def invoke(self, _prompt):
            self.calls += 1
            raise ServiceError("mensaje privado del proveedor")

    output = tmp_path / "result.json"
    model = BrokenModel()
    with pytest.raises(ServiceError):
        execute_v7_trial(document("PRIMERA: El locador conserva el edificio."), model, output, metadata={})
    text = output.read_text(encoding="utf-8")
    assert "mensaje privado" not in text
    assert json.loads(text)["error"]["http_status"] == 503
    assert model.calls == 1


def test_incomplete_document_never_calls_model():
    model = FakeModel()
    extracted = ContractText([PageText(1, "", "sin_lectura", False)], False)
    with pytest.raises(SegmentedInputError):
        evaluate_v7_with_model(extracted, model)
    assert model.calls == 0
