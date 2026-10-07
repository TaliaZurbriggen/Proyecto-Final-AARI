"""Comparación controlada de modelo, sin entrada distinta ni resultados pisados."""

from copy import deepcopy

import pytest

from app.services.contract_clause_corpus import load_json, verify_prompt_freeze
from app.services.contract_clause_reference_trial import execute_reference_trial
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_clause_v9 import evaluate_v9_with_model
from app.services.contract_text_extraction import ContractText, PageText
from scripts import evaluate_contract_clause_v9_comparison as flash35
from scripts import evaluate_contract_clause_v9_flash38 as flash38


@pytest.fixture(params=(flash35, flash38), ids=("flash35", "flash38"))
def comparison(request):
    return request.param


def manifests(comparison):
    return load_json(comparison.MANIFEST), load_json(comparison.BASELINE_MANIFEST)


def input_pair(comparison):
    previous = load_json(comparison.BASELINE_RESULT)
    current = deepcopy(previous)
    current["model"] = comparison.COMPARISON_MODEL
    return current, previous


def test_comparison_manifest_changes_only_model_and_registry(comparison):
    current, previous = manifests(comparison)
    comparison.validate_comparison_manifest(current, previous)
    verify_prompt_freeze(current, comparison.PROJECT)
    verify_prompt_freeze(previous, comparison.PROJECT)


@pytest.mark.parametrize("field", ["model", "prompt_version", "thresholds", "documents", "ocr", "results_directory"])
def test_comparison_rejects_unapproved_manifest_changes(comparison, field):
    current, previous = manifests(comparison)
    if field == "model":
        current["prompt_freeze"][field] = "modelo-no-autorizado"
    elif field == "prompt_version":
        current["prompt_freeze"][field] = "otra-version"
    elif field == "results_directory":
        current[field] = previous[field]
    else:
        current[field] = None
    with pytest.raises(ValueError):
        comparison.validate_comparison_manifest(current, previous)


def test_comparison_rejects_changed_frozen_pipeline(comparison):
    current, previous = manifests(comparison)
    target = previous["prompt_freeze"]["files"][0]["path"]
    for item in current["prompt_freeze"]["files"]:
        if item["path"] == target:
            item["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="archivo congelado"):
        comparison.validate_comparison_manifest(current, previous)


def test_comparison_accepts_identical_input_with_different_model(comparison):
    current, previous = input_pair(comparison)
    comparison.validate_same_input(current, previous)


@pytest.mark.parametrize("field", [
    "source_sha256", "source_characters", "prompt_characters",
    "extracted_pages_sha256", "ocr_language",
])
def test_comparison_rejects_different_input_before_model(comparison, field):
    current, previous = input_pair(comparison)
    current[field] = "diferente"
    with pytest.raises(ValueError, match="entrada no coincide"):
        comparison.validate_same_input(current, previous)


def test_comparison_requires_completed_reference(comparison):
    current, previous = input_pair(comparison)
    previous["state"] = "failed"
    with pytest.raises(ValueError, match="referencia Flash-Lite"):
        comparison.validate_same_input(current, previous)


def test_comparison_result_is_separate_and_never_repeats(comparison, tmp_path):
    class Fake:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            assert "v9 experimental" in prompt
            return {"clausulas": [{
                "tramo_id": 1, "resumen": "El ocupante avisa los daños.",
                "categoria": "aviso", "responsable": "inquilino",
                "uso_clasificador": "operativa", "confianza": 0.9,
            }]}

    source = ContractText([PageText(1, "PRIMERA: El ocupante avisa los daños.", "digital", True)], True)
    old = tmp_path / "lite.json"
    old.write_text("referencia preservada", encoding="utf-8")
    new = tmp_path / "flash.json"
    model = Fake()
    result = execute_reference_trial(
        source, model, new, metadata={"model": comparison.COMPARISON_MODEL},
        evaluate=evaluate_v9_with_model,
    )
    assert result["model"] == comparison.COMPARISON_MODEL
    assert result["source_preserved"] is True
    assert result["adapter_invocations"] == 1
    assert old.read_text(encoding="utf-8") == "referencia preservada"
    with pytest.raises(TrialAlreadyRecorded):
        execute_reference_trial(source, model, new, metadata={}, evaluate=evaluate_v9_with_model)
    assert model.calls == 1


def test_both_models_use_same_structured_adapter_configuration(comparison, monkeypatch):
    from app.services import contract_clause_v7 as adapter

    captured = []

    class Stub:
        def __init__(self, **configuration):
            captured.append(configuration)

        def with_structured_output(self, schema, *, method):
            assert schema is adapter.SourceClauseBatch
            assert method == "function_calling"
            return self

    monkeypatch.setenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-ficticio-local")
    monkeypatch.setattr(adapter, "ChatGoogleGenerativeAI", Stub)
    adapter.get_v7_model("gemini-3.5-flash-lite")
    adapter.get_v7_model(comparison.COMPARISON_MODEL)
    assert captured[0].pop("model") == "gemini-3.5-flash-lite"
    assert captured[1].pop("model") == comparison.COMPARISON_MODEL
    assert captured[0] == captured[1]
    assert captured[0]["max_retries"] == 1


def test_comparisons_have_independent_registries_and_same_frozen_input():
    first = load_json(flash35.MANIFEST)
    second = load_json(flash38.MANIFEST)
    assert first["results_directory"] != second["results_directory"]
    assert first["prompt_freeze"]["prompt_version"] == second["prompt_freeze"]["prompt_version"]
    assert first["documents"] == second["documents"]
    assert first["thresholds"] == second["thresholds"]
    assert flash35.BASELINE_RESULT == flash38.BASELINE_RESULT
    actual = {item["path"]: item["sha256"] for item in second["prompt_freeze"]["files"]}
    for item in first["prompt_freeze"]["files"]:
        assert actual[item["path"]] == item["sha256"]
