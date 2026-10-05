"""El ensayo v6 preserva evidencia y no repite una llamada iniciada."""

import json

import pytest

from app.services.contract_clause_v5 import SegmentedInputError
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_clause_v6_trial import execute_v6_trial
from app.services.contract_text_extraction import ContractText, PageText


class FakeModel:
    calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return {"clausulas": []}


def test_v6_preserves_completed_trial_and_never_overwrites_it(tmp_path):
    model = FakeModel()
    source = ContractText([PageText(1, "QUINTA: El locador mantiene el edificio.", "digital", True)], True)
    output = tmp_path / "result.json"

    result = execute_v6_trial(source, model, output, metadata={"document": "V04"})
    assert result["state"] == "completed"
    assert result["source_preserved"] is True
    with pytest.raises(TrialAlreadyRecorded):
        execute_v6_trial(source, model, output, metadata={})
    assert model.calls == 1


def test_v6_failed_trial_records_status_without_private_message(tmp_path):
    class ServiceError(Exception):
        code = 503

    class BrokenModel(FakeModel):
        def invoke(self, _prompt):
            self.calls += 1
            raise ServiceError("mensaje privado del proveedor")

    model = BrokenModel()
    source = ContractText([PageText(1, "QUINTA: El locador mantiene el edificio.", "digital", True)], True)
    output = tmp_path / "result.json"
    with pytest.raises(ServiceError):
        execute_v6_trial(source, model, output, metadata={})
    saved = output.read_text(encoding="utf-8")
    assert "mensaje privado" not in saved
    assert json.loads(saved)["error"] == {"type": "ServiceError", "http_status": 503}
    assert model.calls == 1


def test_v6_unreadable_page_prevents_call_and_checkpoint(tmp_path):
    model = FakeModel()
    source = ContractText([PageText(1, "", "sin_lectura", False)], False)
    output = tmp_path / "result.json"
    with pytest.raises(SegmentedInputError):
        execute_v6_trial(source, model, output, metadata={})
    assert model.calls == 0
    assert not output.exists()
