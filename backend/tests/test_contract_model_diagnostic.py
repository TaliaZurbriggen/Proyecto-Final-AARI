"""El diagnóstico mínimo respeta autorización, privacidad y checkpoints."""

import json
from types import SimpleNamespace

import pytest

from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from scripts import diagnose_contract_model_flash38 as probe


class Fake:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = 0
        self.prompts = []

    def invoke(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.output


def test_second_probe_runs_only_after_plain_response_with_identical_prompt(tmp_path):
    plain = Fake(SimpleNamespace(content="OK"))
    structured = Fake(probe.ProbeResponse(respuesta="OK"))
    result = probe.run_diagnostic(lambda: plain, lambda: structured, tmp_path, metadata={})
    assert result["adapter_invocations"] == 2
    assert not result["structured_skipped"]
    assert plain.prompts == structured.prompts == [probe.PROMPT]
    assert all(item["expected_ok"] for item in result["trials"])


def test_plain_error_stops_without_constructing_structured_model(tmp_path):
    class ServerError(Exception):
        code = 503

    plain = Fake(error=ServerError("high demand; contenido privado"))

    def forbidden_factory():
        pytest.fail("No debe prepararse la segunda invocación.")

    result = probe.run_diagnostic(lambda: plain, forbidden_factory, tmp_path, metadata={})
    assert result["adapter_invocations"] == plain.calls == 1
    assert result["structured_skipped"]
    assert result["trials"][0]["error"]["http_status"] == 503
    assert result["trials"][0]["error"]["reason_category"] == "high_demand"
    assert "contenido privado" not in (tmp_path / "plain.json").read_text(encoding="utf-8")
    assert not (tmp_path / "structured.json").exists()


def test_structured_error_has_no_retry(tmp_path):
    plain = Fake(SimpleNamespace(content="OK"))
    structured = Fake(error=RuntimeError("mensaje privado"))
    result = probe.run_diagnostic(lambda: plain, lambda: structured, tmp_path, metadata={})
    assert result["adapter_invocations"] == 2
    assert structured.calls == 1
    assert result["trials"][1]["state"] == "failed"
    assert "mensaje privado" not in (tmp_path / "structured.json").read_text(encoding="utf-8")


def test_empty_plain_response_stops_before_second_probe(tmp_path):
    plain = Fake(SimpleNamespace(content=""))
    structured = Fake(probe.ProbeResponse(respuesta="OK"))
    result = probe.run_diagnostic(lambda: plain, lambda: structured, tmp_path, metadata={})
    assert result["structured_skipped"]
    assert structured.calls == 0


@pytest.mark.parametrize("filename", ["plain.json", "structured.json"])
def test_existing_evidence_prevents_all_calls(tmp_path, filename):
    (tmp_path / filename).write_text("registro preservado", encoding="utf-8")
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_diagnostic(lambda: pytest.fail("No debe llamarse"), lambda: None, tmp_path, metadata={})
    assert (tmp_path / filename).read_text(encoding="utf-8") == "registro preservado"


def test_adapter_changes_only_structured_binding(monkeypatch):
    configured = []

    class Stub:
        def __init__(self, **kwargs):
            configured.append(kwargs)

        def with_structured_output(self, schema, *, method):
            assert schema is probe.ProbeResponse
            assert method == "function_calling"
            return self

    monkeypatch.setattr(probe, "ChatGoogleGenerativeAI", Stub)
    probe.build_model("valor-ficticio", structured=False)
    probe.build_model("valor-ficticio", structured=True)
    assert configured[0] == configured[1]
    assert configured[0]["model"] == "gemini-3.8-flash"
    assert configured[0]["max_retries"] == 1


def test_unexpected_reply_is_not_persisted(tmp_path):
    result = probe.execute_probe(
        lambda: Fake(SimpleNamespace(content="texto privado no esperado")),
        tmp_path / "plain.json", structured=False, metadata={},
    )
    assert result["response_received"]
    assert not result["expected_ok"]
    assert result["safe_response"] is None
    assert "texto privado" not in (tmp_path / "plain.json").read_text(encoding="utf-8")


def test_checkpoint_precedes_invocation_and_content_blocks_are_supported(tmp_path):
    path = tmp_path / "plain.json"

    class Inspect:
        def invoke(self, prompt):
            assert json.loads(path.read_text(encoding="utf-8"))["state"] == "started"
            return SimpleNamespace(content=[{"type": "text", "text": "OK"}])

    result = probe.execute_probe(lambda: Inspect(), path, structured=False, metadata={})
    assert result["expected_ok"]
    assert result["adapter_invocations"] == 1
