"""El ensayo autorizado registra una sola invocación y nunca reintenta."""

import json

import pytest

from app.services.contract_clause_v5 import SegmentedInputError
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded, execute_v5_trial
from app.services.contract_text_extraction import ContractText, PageText
from scripts.evaluate_contract_clause_v5 import RESULTS_BY_MODEL


SOURCE = "QUINTA: El locador debe reparar el inmueble durante la vigencia del contrato."


def test_flash_trial_has_its_own_checkpoint_without_replacing_flash_lite():
    assert RESULTS_BY_MODEL["gemini-3.5-flash-lite"].name == "resultado_v04_v5.json"
    assert RESULTS_BY_MODEL["gemini-3.5-flash"].name == "resultado_v04_v5_flash.json"
    assert len(set(RESULTS_BY_MODEL.values())) == 2


def extracted(*, readable=True):
    return ContractText([PageText(1, SOURCE if readable else "", "digital", readable)], readable)


class FakeModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        assert "[TRAMO 1 | CLÁUSULA 5]" in prompt
        return {"clausulas": [{
            "numero": "QUINTA", "titulo": "Reparación",
            "evidencias": [{
                "pagina": 1,
                "texto": "El locador debe reparar el inmueble durante la vigencia del contrato",
            }],
            "resumen": "El locador debe reparar el inmueble durante la vigencia.",
            "categoria": "reparacion", "responsable": "propietario",
            "uso_clasificador": "operativa", "condiciones": None,
            "referencias": [], "confianza": 0.8,
        }]}


def test_success_saves_utf8_proposals_and_prevents_second_call(tmp_path):
    output = tmp_path / "resultado.json"
    model = FakeModel()

    result = execute_v5_trial(extracted(), model, output, metadata={"document": "V04"})

    assert model.calls == 1
    assert result["state"] == "completed"
    assert result["model_proposals"] == 1
    assert len(result["valid_clauses"]) == 1
    assert result["source_preserved"] is True
    saved = output.read_text(encoding="utf-8")
    assert "Reparación" in saved and "\ufffd" not in saved
    assert json.loads(saved)["proposals"][0]["titulo"] == "Reparación"

    with pytest.raises(TrialAlreadyRecorded):
        execute_v5_trial(extracted(), model, output, metadata={"document": "V04"})
    assert model.calls == 1


def test_failure_keeps_safe_checkpoint_and_does_not_retry(tmp_path):
    output = tmp_path / "resultado.json"

    class BrokenModel:
        calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            raise RuntimeError("texto privado que no debe quedar registrado")

    model = BrokenModel()
    with pytest.raises(RuntimeError):
        execute_v5_trial(extracted(), model, output, metadata={"document": "V04"})

    saved = output.read_text(encoding="utf-8")
    record = json.loads(saved)
    assert model.calls == 1
    assert record["state"] == "failed"
    assert record["adapter_invocations"] == 1
    assert record["error"] == {"type": "RuntimeError"}
    assert "texto privado" not in saved

    with pytest.raises(TrialAlreadyRecorded):
        execute_v5_trial(extracted(), model, output, metadata={"document": "V04"})
    assert model.calls == 1


def test_preflight_failure_does_not_create_checkpoint_or_call_model(tmp_path):
    output = tmp_path / "resultado.json"
    model = FakeModel()

    with pytest.raises(SegmentedInputError):
        execute_v5_trial(extracted(readable=False), model, output, metadata={})

    assert not output.exists()
    assert model.calls == 0
