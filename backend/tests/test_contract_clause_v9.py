"""V9 utiliza el prompt de coherencia sin modificar fuente ni respuestas del modelo."""

import json
from pathlib import Path

import pytest

from app.services.contract_clause_corpus import load_json, verify_prompt_freeze
from app.services.contract_clause_reference_trial import execute_reference_trial
from app.services.contract_clause_v5 import SegmentedInputError, build_segmented_input
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services import contract_clause_v9 as v9
from app.services.contract_text_extraction import ContractText, PageText


PROJECT = Path(__file__).resolve().parents[2]


def document(*texts):
    return ContractText([PageText(i, text, "digital", True) for i, text in enumerate(texts, 1)], True)


def proposal(**overrides):
    return {
        "tramo_id": 1, "titulo": "Reparación condicionada",
        "resumen": "El ocupante repara los daños causados por su uso indebido.",
        "categoria": "danio", "responsable": "inquilino",
        "uso_clasificador": "operativa", "condiciones": "Sólo por uso indebido.",
        "referencias": [], "confianza": 0.9, **overrides,
    }


class FakeModel:
    def __init__(self, payload, check=None):
        self.payload = payload
        self.check = check
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        assert "v9 experimental" in prompt
        assert "Coherencia de todos los campos ante incertidumbre" in prompt
        if self.check is not None:
            self.check(prompt)
        return self.payload


def test_v9_prompt_keeps_source_ids_and_requires_consistency_in_both_fields():
    source = document("PRIMERA: El ocupante avisa los daños. DNI 00000000.")
    prepared = build_segmented_input(source)
    prompt = v9.build_v9_prompt(prepared)
    assert "[TRAMO 1" in prompt
    assert "[PÁGINA 1]" in prompt
    assert "{{TEXTO_CONTRATO}}" not in prompt
    assert "00000000" not in prompt
    assert "[IDENTIFICADOR OMITIDO]" in prompt
    assert "No resuelvas en un campo lo" in prompt
    assert "explicá las lecturas posibles" in prompt
    assert "sin introducir incertidumbre artificial" in prompt
    assert prepared.reconstructed_pages() == {1: source.pages[0].text}


@pytest.mark.parametrize("template", ["sin marcador", "{{TEXTO_CONTRATO}} {{TEXTO_CONTRATO}}"])
def test_v9_rejects_missing_or_duplicate_placeholder_before_model(tmp_path, monkeypatch, template):
    path = tmp_path / "prompt.md"
    path.write_text(template, encoding="utf-8")
    monkeypatch.setattr(v9, "PROMPT_PATH", path)
    model = FakeModel({"clausulas": []})
    with pytest.raises(ValueError, match="marcador único"):
        v9.evaluate_v9_with_model(document("PRIMERA: El ocupante avisa los daños."), model)
    assert model.calls == 0


def test_v9_preserves_clear_conditional_rule_cross_page_evidence_and_checkpoint(tmp_path):
    source = document(
        "PRIMERA: El ocupante repara daños causados",
        "por su uso indebido.\nSEGUNDA: El locador conserva el techo.",
    )
    path = tmp_path / "result.json"

    def check_checkpoint(_prompt):
        assert json.loads(path.read_text(encoding="utf-8"))["state"] == "started"

    payload = proposal()
    model = FakeModel({"clausulas": [payload]}, check_checkpoint)
    result = execute_reference_trial(
        source, model, path, metadata={"prompt_version": v9.PROMPT_VERSION},
        evaluate=v9.evaluate_v9_with_model,
    )
    clause = result["valid_clauses"][0]
    assert result["source_preserved"] is True
    assert result["proposals"][0] == payload
    assert clause["paginas"] == [1, 2]
    assert clause["uso_clasificador"] == "operativa"
    assert clause["condiciones"] == payload["condiciones"]
    assert "uso indebido" in clause["texto_original"]
    assert "SEGUNDA" not in clause["texto_original"]
    with pytest.raises(TrialAlreadyRecorded):
        execute_reference_trial(source, model, path, metadata={}, evaluate=v9.evaluate_v9_with_model)
    assert model.calls == 1


def test_v9_preserves_neutral_ambiguous_output_and_explicit_uncertainty():
    source = document("PRIMERA: A coordina X, excepto Y cuando C, y Z.")
    payload = proposal(
        titulo="Alcance de tareas", categoria="reparacion", responsable="no_especificado",
        uso_clasificador="contexto", confianza=0.6,
        resumen="El texto menciona X, Y y Z sin precisar el alcance de Z.",
        condiciones="No se determina si Z integra la obligación principal o la excepción.",
    )
    result = v9.evaluate_v9_with_model(source, FakeModel({"clausulas": [payload]}))
    clause = result.accepted[0]
    assert clause.responsable == "no_especificado"
    assert clause.uso_clasificador == "contexto"
    assert clause.confianza == 0.6
    assert clause.resumen == payload["resumen"]
    assert clause.condiciones == payload["condiciones"]
    assert clause.texto_original == source.pages[0].text


def test_v9_does_not_rewrite_inconsistent_model_output_into_expected_answer():
    source = document("PRIMERA: A coordina X, excepto Y cuando C, y Z.")
    payload = proposal(
        responsable="no_especificado", uso_clasificador="contexto", confianza=0.6,
        resumen="El alcance de la lista es ambiguo.",
        condiciones="Se exceptúan Y bajo C y Z.",
    )
    result = v9.evaluate_v9_with_model(source, FakeModel({"clausulas": [payload]}))
    # Procedencia válida no implica interpretación correcta: la revisión externa
    # debe detectar este problema. El ejecutor no conoce la respuesta esperada.
    assert result.batch.clausulas[0].condiciones == payload["condiciones"]
    assert result.accepted[0].condiciones == payload["condiciones"]


@pytest.mark.parametrize("source", [
    ContractText([PageText(1, "", "sin_lectura", False)], False),
    document("Texto legible sin encabezados reconocibles."),
])
def test_v9_rejects_unusable_source_before_checkpoint_and_model(tmp_path, source):
    path = tmp_path / "result.json"
    model = FakeModel({"clausulas": []})
    with pytest.raises((SegmentedInputError, ValueError)):
        execute_reference_trial(source, model, path, metadata={}, evaluate=v9.evaluate_v9_with_model)
    assert model.calls == 0
    assert not path.exists()


def test_v9_manifest_keeps_previous_versions_and_controls_frozen():
    previous = load_json(PROJECT / "docs/evaluaciones/hu30/corpus_v8_manifest.json")
    current = load_json(PROJECT / "docs/evaluaciones/hu30/corpus_v9_manifest.json")
    verify_prompt_freeze(previous, PROJECT)
    verify_prompt_freeze(current, PROJECT)
    assert current["thresholds"] == previous["thresholds"]
    assert current["documents"] == previous["documents"]
    assert current["ocr"] == previous["ocr"]
    by_path = {item["path"]: item["sha256"] for item in current["prompt_freeze"]["files"]}
    for item in previous["prompt_freeze"]["files"]:
        assert by_path[item["path"]] == item["sha256"]
