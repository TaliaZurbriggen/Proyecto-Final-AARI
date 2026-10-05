"""Comparación controlada del prompt breve sin API externa."""

import json

import pytest

from app.services.contract_clause_corpus import load_json
from app.services.contract_clause_v5 import build_segmented_input
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from scripts import diagnose_contract_short_prompt_flash38 as probe


PAYLOAD = {"clausulas": [{
    "tramo_id": 2, "titulo": "Daños por uso indebido",
    "resumen": "El inquilino debe reparar los daños que haya causado por uso indebido.",
    "categoria": "danio", "responsable": "inquilino", "uso_clasificador": "operativa",
    "condiciones": "Daños causados por el inquilino por uso indebido.",
    "referencias": [], "confianza": 0.9,
}]}


class Fake:
    def __init__(self, path, output=PAYLOAD, error=None):
        self.path, self.output, self.error = path, output, error
        self.calls = 0

    def invoke(self, prompt):
        assert json.loads(self.path.read_text(encoding="utf-8"))["state"] == "started"
        assert prompt.startswith(probe.INSTRUCTIONS)
        assert "v9 experimental" not in prompt
        assert "[TRAMO 1" in prompt and "[TRAMO 2" in prompt
        for line in probe.reference.SYNTHETIC_SOURCE.splitlines():
            assert line in prompt
        self.calls += 1
        if self.error:
            raise self.error
        return self.output


def test_short_prompt_changes_instructions_but_not_segmented_source_or_schema():
    metadata = probe.prepare_metadata()
    baseline = load_json(probe.BASELINE)
    assert metadata["source_sha256"] == baseline["source_sha256"]
    assert metadata["schema_sha256"] == baseline["schema_sha256"]
    assert metadata["packages"] == baseline["packages"]
    assert metadata["prompt_characters"] < 600
    assert metadata["baseline_prompt_characters"] == 6251
    assert metadata["prompt_version"] != baseline["prompt_version"]
    assert not metadata["counts_towards_corpus_metrics"]
    prepared = build_segmented_input(probe.reference.synthetic_document())
    assert metadata["diagnostic_prompt"].endswith(prepared.model_text)


def test_one_invocation_preserves_response_and_attaches_same_source_evidence(tmp_path):
    path = tmp_path / "result.json"
    model = Fake(path)
    result = probe.run_probe(lambda: model, path, metadata={})
    assert model.calls == result["adapter_invocations"] == 1
    assert result["state"] == "completed" and result["source_preserved"]
    assert result["proposals"] == PAYLOAD["clausulas"]
    assert result["valid_clauses"][0]["texto_original"] == probe.reference.SYNTHETIC_SOURCE.splitlines()[1]


@pytest.mark.parametrize("state", ["started", "completed", "failed"])
def test_existing_checkpoint_forbids_model_construction(tmp_path, state):
    path = tmp_path / "result.json"
    original = json.dumps({"state": state})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_probe(lambda: pytest.fail("No construir el modelo"), path, metadata={})
    assert path.read_text(encoding="utf-8") == original


def test_failure_records_only_safe_error_and_never_retries(tmp_path):
    class ServerError(Exception):
        code = 503

    path = tmp_path / "result.json"
    model = Fake(path, error=ServerError("mensaje privado"))
    with pytest.raises(ServerError):
        probe.run_probe(lambda: model, path, metadata={})
    record = json.loads(path.read_text(encoding="utf-8"))
    assert model.calls == record["adapter_invocations"] == 1
    assert record["error"] == {"type": "ServerError", "http_status": 503}
    assert "mensaje privado" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("field", ["source_sha256", "schema_sha256", "model", "packages"])
def test_changed_comparison_constant_aborts_before_api(field):
    metadata = probe.reference.prepare_metadata()
    metadata[field] = "valor-distinto"
    with pytest.raises(ValueError, match="configuración"):
        probe.validate_same_configuration(metadata, load_json(probe.BASELINE))


def test_empty_response_is_not_presented_as_a_successful_extraction(tmp_path):
    path = tmp_path / "result.json"
    model = Fake(path, output={"clausulas": []})
    result = probe.run_probe(lambda: model, path, metadata={})
    assert model.calls == 1
    assert result["state"] == "completed"
    assert result["model_proposals"] == 0 and result["valid_clauses"] == []


def test_malformed_response_is_failed_and_not_retried(tmp_path):
    path = tmp_path / "result.json"
    model = Fake(path, output={"clausulas": [{"tramo_id": 1}]})
    with pytest.raises(ValueError):
        probe.run_probe(lambda: model, path, metadata={})
    assert model.calls == 1
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "failed"
