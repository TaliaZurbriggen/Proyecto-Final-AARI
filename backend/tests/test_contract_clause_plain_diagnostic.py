"""El ensayo mínimo no oculta reintentos ni modifica evidencia previa."""

import json

import httpx
import pytest

from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from scripts import diagnose_contract_clause_plain as probe


def test_preparation_only_sends_complete_public_clause_without_expected_answers():
    prompt, metadata = probe.prepare_probe()
    assert metadata["document"] == "V04" and metadata["tramo_id"] == 5
    assert metadata["source_pages"] == [1, 2]
    assert metadata["clause_characters"] == 379
    assert len(prompt) < 750
    assert metadata["source_clause"] in prompt
    assert "V04-E01" not in prompt and "clausulas" not in prompt and "JSON" not in prompt
    assert not metadata["counts_towards_corpus_metrics"]


def test_sdk_single_real_transport_invocation_and_evidence_preserved(monkeypatch, tmp_path):
    path = tmp_path / "result.json"
    original_client = probe.direct.genai.Client
    bodies = []

    def handler(request):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["state"] == "started" and record["sdk_invocations"] == 1
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{
            "content": {"role": "model", "parts": [{"text": "Interpretación simulada."}]},
            "finishReason": "STOP",
        }]})

    def factory(**kwargs):
        options = kwargs["http_options"]
        assert options.retry_options.attempts == 1
        options.client_args["transport"] = httpx.MockTransport(handler)
        options.client_args["trust_env"] = False
        return original_client(**kwargs)

    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-value-not-a-secret")
    monkeypatch.setattr(probe.direct.genai, "Client", factory)
    result = probe.run_probe("Texto público.", {"source_clause": "literal"}, path)
    assert result["state"] == "completed" and result["response_received"]
    assert result["http_requests"] == len(bodies) == 1
    assert "tools" not in bodies[0] and "toolConfig" not in bodies[0]
    assert "responseMimeType" not in bodies[0].get("generationConfig", {})
    assert result["source_clause"] == "literal" and result["semantic_review"] == "pending"


@pytest.mark.parametrize("state", ["started", "completed", "failed"])
def test_checkpoint_prevents_another_call(tmp_path, state):
    path = tmp_path / "result.json"
    original = json.dumps({"state": state})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_probe("prompt", {}, path, client_factory=lambda _: pytest.fail("No API"))
    assert path.read_text(encoding="utf-8") == original


def test_counter_blocks_a_second_request():
    counter = probe.SingleRequestCounter()
    request = httpx.Request("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{probe.direct.MODEL}:generateContent")
    counter.on_request(request)
    with pytest.raises(RuntimeError):
        counter.on_request(request)
    assert counter.attempts == 1


def test_error_only_records_known_safe_category():
    class Error(Exception):
        code = 503
        message = "High demand, private info that must not be persisted"
    assert probe.safe_error(Error()) == {
        "type": "Error", "http_status": 503, "provider_message_category": "high_demand",
    }
