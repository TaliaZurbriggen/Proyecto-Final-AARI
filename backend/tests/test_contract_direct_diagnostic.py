"""Diagnóstico directo: SDK real con transporte simulado, sin red ni cuota."""

import json

from google import genai
import httpx
import pytest

from app.services.contract_clause_v5 import build_segmented_input
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_text_extraction import ContractText, PageText
from scripts import diagnose_contract_direct_gemini as probe


PAYLOAD = {"clausulas": [{
    "tramo_id": 2, "titulo": "Daños por uso indebido",
    "resumen": "El inquilino repara los daños causados por uso indebido.",
    "categoria": "danio", "responsable": "inquilino", "uso_clasificador": "operativa",
    "condiciones": "Daños por uso indebido.", "referencias": [], "confianza": 0.9,
}]}
SOURCE = (
    "PRIMERA: El propietario conserva el inmueble apto para el uso acordado.\n"
    "SEGUNDA: El inquilino repara los daños que cause por uso indebido."
)


def document():
    return ContractText([PageText(1, SOURCE, "digital", True)], True)


def mock_google(monkeypatch, path, outputs):
    """Cuenta el transporte del SDK, no sólo invocaciones del adaptador."""
    original_client = genai.Client
    requests = []

    def handler(request):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["stages"][-1]["state"] == "started"
        assert record["sdk_invocations"] == len(requests) + 1
        body = json.loads(request.content)
        requests.append(body)
        output = outputs[len(requests) - 1]
        if isinstance(output, Exception):
            raise output
        if isinstance(output, int):
            return httpx.Response(output, json={"error": {
                "code": output, "message": "mensaje que no debe guardarse", "status": "UNAVAILABLE",
            }})
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": output}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 80, "totalTokenCount": 180},
        })

    def factory(**kwargs):
        options = kwargs["http_options"]
        assert options.retry_options.attempts == 1
        assert options.timeout == probe.TIMEOUT_MS
        assert kwargs["vertexai"] is False
        options.client_args["transport"] = httpx.MockTransport(handler)
        options.client_args["trust_env"] = False
        return original_client(**kwargs)

    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-value-not-a-secret")
    monkeypatch.setattr(probe.genai, "Client", factory)
    return requests


def test_configs_have_no_tools_and_only_requested_format_changes():
    configs = [probe.stage_config(mode).model_dump(exclude_none=True) for mode in probe.MODES]
    for config in configs:
        assert not config.get("tools") and not config.get("tool_config")
        assert config["automatic_function_calling"]["disable"] is True
        assert "temperature" not in config
    assert "response_mime_type" not in configs[0]
    assert configs[1]["response_mime_type"] == configs[2]["response_mime_type"] == "application/json"
    assert "response_json_schema" not in configs[1]
    assert configs[2]["response_json_schema"] == probe.native_schema()
    with pytest.raises(ValueError):
        probe.stage_config("function_calling")


def test_native_schema_keeps_nine_fields_enums_nulls_and_local_limits():
    schema = probe.native_schema()
    proposal = schema["properties"]["clausulas"]["items"]
    assert set(proposal["properties"]) == {
        "tramo_id", "titulo", "resumen", "categoria", "responsable", "uso_clasificador",
        "condiciones", "referencias", "confianza",
    }
    assert set(proposal["required"]) == set(proposal["properties"])
    assert proposal["properties"]["titulo"]["type"] == ["string", "null"]
    assert proposal["properties"]["confianza"]["maximum"] == 1
    assert "no_especificado" in proposal["properties"]["responsable"]["enum"]
    assert "$ref" not in json.dumps(schema) and "$defs" not in json.dumps(schema)
    invalid = json.loads(json.dumps(PAYLOAD))
    invalid["clausulas"][0]["resumen"] = "x" * 1201
    result = probe.validate_response(json.dumps(invalid), build_segmented_input(document()))
    assert result["validation_error"] == "local_schema"


def test_three_modes_same_prompt_one_http_each_with_original_evidence(monkeypatch, tmp_path):
    path = tmp_path / "result.json"
    requests = mock_google(monkeypatch, path, [json.dumps(PAYLOAD)] * 3)
    result = probe.run_diagnostic(document(), path, metadata={})
    assert result["state"] == "completed"
    assert result["http_requests"] == result["sdk_invocations"] == len(requests) == 3
    assert len({stage["prompt_sha256"] for stage in result["stages"]}) == 1
    assert all(request["contents"] == requests[0]["contents"] for request in requests)
    assert all("tools" not in request and "toolConfig" not in request for request in requests)
    assert "responseMimeType" not in requests[0].get("generationConfig", {})
    assert requests[1]["generationConfig"]["responseMimeType"] == "application/json"
    assert requests[2]["generationConfig"]["responseJsonSchema"] == probe.native_schema()
    assert result["source_preserved"] and not result["counts_towards_corpus_metrics"]
    for stage in result["stages"]:
        assert stage["http_requests"] == 1 and stage["http_statuses"] == [200]
        assert stage["raw_json"] == PAYLOAD
        assert stage["valid_clauses"][0]["texto_original"] == SOURCE.splitlines()[1]
        assert stage["semantic_review"] == "pending"


@pytest.mark.parametrize("status", [400, 429, 500, 503])
def test_errors_stop_immediately_without_sdk_retry_or_next_mode(monkeypatch, tmp_path, status):
    path = tmp_path / "result.json"
    requests = mock_google(monkeypatch, path, [status, json.dumps(PAYLOAD)])
    result = probe.run_diagnostic(document(), path, metadata={})
    assert result["state"] == "failed" and result["stop_reason"] == "request_error_no_retry"
    assert len(requests) == result["http_requests"] == result["sdk_invocations"] == 1
    assert result["stages"][0]["error"]["http_status"] == status
    saved = path.read_text(encoding="utf-8")
    assert "mensaje que no debe guardarse" not in saved
    assert "fake-test-value-not-a-secret" not in saved


def test_transport_timeout_is_recorded_and_does_not_retry(monkeypatch, tmp_path):
    path = tmp_path / "result.json"
    requests = mock_google(monkeypatch, path, [httpx.ReadTimeout("private details")])
    result = probe.run_diagnostic(document(), path, metadata={})
    assert len(requests) == result["http_requests"] == 1
    assert result["stages"][0]["error"]["type"] == "ReadTimeout"
    assert "private details" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("state", ["started", "completed", "failed"])
def test_existing_checkpoint_blocks_client_construction(tmp_path, state):
    path = tmp_path / "result.json"
    original = json.dumps({"state": state})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_diagnostic(document(), path, metadata={}, client_factory=lambda _: pytest.fail("No API"))
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("output", ["", "{}", '{"clausulas": []}', '{"clausulas": [{"tramo_id": 1}]}'])
def test_unusable_json_is_not_success_and_prevents_schema_stage(monkeypatch, tmp_path, output):
    path = tmp_path / "result.json"
    requests = mock_google(monkeypatch, path, [json.dumps(PAYLOAD), output, json.dumps(PAYLOAD)])
    result = probe.run_diagnostic(document(), path, metadata={})
    assert result["state"] == "stopped" and len(requests) == 2
    assert result["http_requests"] == 2


def test_plain_markdown_can_be_followed_by_json_but_is_not_claimed_valid(monkeypatch, tmp_path):
    path = tmp_path / "result.json"
    markdown = "```json\n" + json.dumps(PAYLOAD) + "\n```"
    mock_google(monkeypatch, path, [markdown, json.dumps(PAYLOAD), json.dumps(PAYLOAD)])
    result = probe.run_diagnostic(document(), path, metadata={})
    assert result["state"] == "completed"
    assert result["stages"][0]["raw_text"] == markdown
    assert result["stages"][0]["validation_error"] == "not_json"
    assert not result["stages"][0]["format_valid"]


def test_unknown_source_segment_preserves_rejection_without_fabricating_evidence():
    unknown = json.loads(json.dumps(PAYLOAD))
    unknown["clausulas"][0]["tramo_id"] = 99
    result = probe.validate_response(json.dumps(unknown), build_segmented_input(document()))
    assert result["format_valid"] and not result["has_usable_clauses"]
    assert result["valid_clauses"] == []
    assert result["rejected_proposals"][0]["propuesta"]["tramo_id"] == 99


def test_counter_rejects_wrong_host_or_fourth_request():
    counter = probe.HttpCounter()
    with pytest.raises(RuntimeError):
        counter.on_request(httpx.Request("POST", "https://example.com/models/other:generateContent"))
    assert counter.attempts == 0
    request = httpx.Request("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{probe.MODEL}:generateContent")
    for _ in range(3):
        counter.on_request(request)
    with pytest.raises(RuntimeError):
        counter.on_request(request)
    assert counter.attempts == 3


def test_preflight_does_not_construct_client_or_write_results(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(probe, "RESULT", tmp_path / "result.json")
    monkeypatch.setattr(probe, "prepare", lambda: (document(), {"document": "V04"}))
    monkeypatch.setattr(probe.genai, "Client", lambda **_: pytest.fail("No API"))
    monkeypatch.setattr("sys.argv", ["diagnose_contract_direct_gemini.py"])
    assert probe.main() == 0
    assert json.loads(capsys.readouterr().out)["external_calls"] == 0
    assert not probe.RESULT.exists()
