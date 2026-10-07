"""Diagnóstico sintético: esquema completo, entrada congelada y máximo una llamada."""

import hashlib
import json

import pytest

from app.services import contract_clause_v7 as v7
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from scripts import diagnose_contract_schema_flash38 as probe


def payload():
    return {"clausulas": [{
        "tramo_id": 1, "titulo": "Filtraciones del techo",
        "resumen": "El propietario repara las filtraciones del techo.",
        "categoria": "reparacion", "responsable": "propietario",
        "uso_clasificador": "operativa", "condiciones": None,
        "referencias": [], "confianza": 0.9,
    }]}


class Fake:
    def __init__(self, path, output=None, error=None):
        self.path, self.output, self.error = path, output, error
        self.calls = 0

    def invoke(self, prompt):
        assert json.loads(self.path.read_text(encoding="utf-8"))["state"] == "started"
        assert "v9 experimental" in prompt
        assert "[TRAMO 1" in prompt and "[TRAMO 2" in prompt
        for line in probe.SYNTHETIC_SOURCE.splitlines():
            assert line in prompt
        self.calls += 1
        if self.error:
            raise self.error
        return self.output


def test_metadata_preserves_frozen_pipeline_full_schema_and_synthetic_source():
    metadata = probe.prepare_metadata()
    assert metadata["model"] == "gemini-3.8-flash"
    assert metadata["source_characters"] == len(probe.SYNTHETIC_SOURCE)
    assert metadata["source_sha256"] == hashlib.sha256(probe.SYNTHETIC_SOURCE.encode()).hexdigest()
    assert metadata["schema_name"] == "SourceClauseBatch"
    assert metadata["structured_output_method"] == "function_calling"
    assert metadata["counts_towards_corpus_metrics"] is False
    assert metadata["real_contracts_sent"] == 0
    frozen = {item["path"]: item["sha256"] for item in metadata["frozen_files"]}
    assert frozen["backend/prompts/prompt_extraccion_clausulas_v9.md"] == (
        "cd1329993efe6187698281426454095cf4bf499755b6b7998e7469f9f707341e"
    )


def test_one_invocation_uses_v9_and_preserves_local_evidence(tmp_path):
    path = tmp_path / "result.json"
    model = Fake(path, payload())
    result = probe.run_probe(lambda: model, path, metadata={"document": "SYNTHETIC-01"})
    assert model.calls == result["adapter_invocations"] == 1
    assert result["authorized_adapter_invocations"] == 1
    assert result["state"] == "completed" and result["source_preserved"]
    assert result["proposals"] == payload()["clausulas"]
    assert result["valid_clauses"][0]["texto_original"] == probe.SYNTHETIC_SOURCE.splitlines()[0]


@pytest.mark.parametrize("state", ["started", "completed", "failed"])
def test_existing_checkpoint_prevents_even_model_construction(tmp_path, state):
    path = tmp_path / "result.json"
    original = json.dumps({"state": state})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_probe(lambda: pytest.fail("No construir el modelo"), path, metadata={})
    assert path.read_text(encoding="utf-8") == original


def test_provider_failure_is_recorded_without_private_message_or_retry(tmp_path):
    class ServerError(Exception):
        code = 503

    path = tmp_path / "result.json"
    model = Fake(path, error=ServerError("mensaje privado"))
    with pytest.raises(ServerError):
        probe.run_probe(lambda: model, path, metadata={})
    record = json.loads(path.read_text(encoding="utf-8"))
    assert model.calls == record["adapter_invocations"] == 1
    assert record["state"] == "failed"
    assert record["error"] == {"type": "ServerError", "http_status": 503}
    assert "mensaje privado" not in path.read_text(encoding="utf-8")


def test_malformed_output_is_failure_not_a_successful_extraction(tmp_path):
    path = tmp_path / "result.json"
    model = Fake(path, {"clausulas": [{"tramo_id": 1}]})
    with pytest.raises(ValueError):
        probe.run_probe(lambda: model, path, metadata={})
    assert model.calls == 1
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "failed"


def test_full_schema_binding_uses_same_model_and_retry_setting(monkeypatch):
    configured = []

    class Stub:
        def __init__(self, **kwargs):
            configured.append(kwargs)

        def with_structured_output(self, schema, *, method):
            assert schema is v7.SourceClauseBatch
            assert method == "function_calling"
            return self

    monkeypatch.setenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-ficticio")
    monkeypatch.setattr(v7, "ChatGoogleGenerativeAI", Stub)
    probe.get_v7_model(probe.MODEL)
    assert configured == [{"model": probe.MODEL, "google_api_key": "valor-ficticio", "max_retries": 1}]


def test_frozen_pipeline_mismatch_aborts_preflight(monkeypatch):
    monkeypatch.setattr(probe, "load_json", lambda _path: {
        "prompt_freeze": {"model": "otro-modelo", "prompt_version": probe.PROMPT_VERSION},
    })
    with pytest.raises(ValueError, match="autorizados"):
        probe.prepare_metadata()
