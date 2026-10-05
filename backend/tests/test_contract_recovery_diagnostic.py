"""Los controles comparables tienen un máximo de una solicitud por caso."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from scripts import diagnose_contract_recovery as probe


def test_lite_uses_exactly_same_public_clause_and_instruction():
    original_prompt, original = probe.single.prepare_probe()
    prompt, lite = probe.prepare("quinta_lite")
    assert prompt == original_prompt and lite["source_clause"] == original["source_clause"]
    assert lite["model"] == "gemini-3.5-flash-lite"
    assert lite["maximum_http_requests"] == 1
    assert not lite["production_changed"]


def test_health_does_not_send_a_contract():
    prompt, metadata = probe.prepare("health38")
    assert prompt == "Respondé solamente OK." and metadata["document"] is None
    assert "source_clause" not in metadata
    with pytest.raises(ValueError):
        probe.prepare("private_document")


def test_full_public_input_same_short_prompt_for_both_json_modes():
    native_prompt, native = probe.prepare("v04_lite_native")
    json_prompt, json_case = probe.prepare("v04_lite_json")
    assert native_prompt == json_prompt
    assert native["source_preserved"] and native["source_characters"] == 4709
    assert native["prompt_version"] == "v10-experimental"
    assert native["model"] == json_case["model"] == "gemini-3.5-flash-lite"
    assert "V04-E" not in native_prompt and "Ejemplo artificial" not in native_prompt
    assert all(f"[TRAMO {i} |" in native_prompt for i in range(1, 13))
    alternative_prompt, alternative = probe.prepare("v04_lite31_json")
    assert alternative_prompt == json_prompt
    assert alternative["source_sha256"] == json_case["source_sha256"]
    assert alternative["model"] == "gemini-3.1-flash-lite"
    flash_prompt, flash = probe.prepare("v04_flash37_json")
    assert flash_prompt == json_prompt
    assert flash["model"] == "gemini-3.7-flash"


def test_lite31_is_validated_locally_like_the_other_full_extractions(monkeypatch, tmp_path):
    path = tmp_path / "result.json"
    prompt, metadata = probe.prepare("v04_lite31_json")
    invalid_output = '{"clausulas": [{"tramo_id": 5}]}'
    response = SimpleNamespace(text=invalid_output, usage_metadata=None)
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: response), close=lambda: None)
    result = probe.run_case(prompt, metadata, path, client_factory=lambda _: client)
    assert result["raw_text"] == invalid_output
    assert not result["format_valid"] and result["validation_error"] == "local_schema"


def test_low_thinking_uses_supported_setting_without_tools_or_sampling_changes():
    mode, config = probe.case_config("v04_flash38_json_low")
    assert mode == "json" and config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.tools is None and config.response_json_schema is None and config.temperature is None


def test_high_thinking_preserves_lite31_prompt_and_changes_only_config():
    prompt, metadata = probe.prepare("v04_lite31_json_high")
    original_prompt, original = probe.prepare("v04_lite31_json")
    assert prompt == original_prompt and metadata["model"] == original["model"]
    mode, high = probe.case_config("v04_lite31_json_high")
    _, baseline = probe.case_config("v04_lite31_json")
    assert mode == "json" and high.thinking_config.thinking_level.value == "HIGH"
    assert high.model_dump(exclude={"thinking_config"}) == baseline.model_dump(exclude={"thinking_config"})


def test_saved_response_validation_keeps_original_and_never_constructs_client(monkeypatch, tmp_path):
    path = tmp_path / "original.json"
    sidecar = tmp_path / "validation.json"
    _, metadata = probe.prepare("v04_lite31_json")
    record = {**metadata, "state": "completed", "raw_text": '{"clausulas": []}'}
    original = json.dumps(record, ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(probe.direct.genai, "Client", lambda **_: pytest.fail("No API"))
    result = probe.validate_saved_case("v04_lite31_json", path, sidecar)
    assert result["external_calls"] == 0 and result["format_valid"]
    assert not result["has_usable_clauses"]
    assert path.read_text(encoding="utf-8") == original
    with pytest.raises(FileExistsError):
        probe.validate_saved_case("v04_lite31_json", path, sidecar)


def test_saved_validation_rejects_changed_input_before_writing(tmp_path):
    path = tmp_path / "original.json"
    _, metadata = probe.prepare("v04_lite31_json")
    path.write_text(json.dumps({**metadata, "source_sha256": "different", "state": "completed", "raw_text": "{}"}))
    with pytest.raises(ValueError, match="evidencia"):
        probe.validate_saved_case("v04_lite31_json", path, tmp_path / "validation.json")
    assert not (tmp_path / "validation.json").exists()


@pytest.mark.parametrize("case", list(probe.CASES))
def test_counter_checks_model_and_blocks_retries(case):
    counter = probe.Counter(probe.CASES[case])
    with pytest.raises(RuntimeError):
        counter.on_request(httpx.Request("POST", "https://example.com/v1beta/models/anything:generateContent"))
    request = httpx.Request("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{counter.model}:generateContent")
    counter.on_request(request)
    with pytest.raises(RuntimeError):
        counter.on_request(request)
    assert counter.attempts == 1


@pytest.mark.parametrize("error", [None, RuntimeError("Do not save private details")])
def test_single_invocation_with_checkpoint_and_safe_failure(tmp_path, error):
    path = tmp_path / "result.json"
    calls = []

    def generate_content(**kwargs):
        assert json.loads(path.read_text())["sdk_invocations"] == 1
        calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(text="OK", usage_metadata=None)

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content), close=lambda: None)
    prompt, metadata = probe.prepare("health38")
    result = probe.run_case(prompt, metadata, path, client_factory=lambda _: client)
    assert len(calls) == 1 and result["state"] == ("failed" if error else "completed")
    assert "Do not save private details" not in path.read_text()
    with pytest.raises(TrialAlreadyRecorded):
        probe.run_case(prompt, metadata, path, client_factory=lambda _: pytest.fail("No API"))
