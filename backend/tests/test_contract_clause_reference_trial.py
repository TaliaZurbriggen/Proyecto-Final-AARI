"""La siguiente versión usa su prompt y preserva checkpoint y fuentes locales."""

import json

import pytest

from app.services.contract_clause_reference_trial import execute_reference_trial
from app.services.contract_clause_v5_trial import TrialAlreadyRecorded
from app.services.contract_clause_v8 import evaluate_v8_with_model
from app.services.contract_text_extraction import ContractText, PageText


SOURCE = ContractText([PageText(1, "PRIMERA: El inmueble se devuelve según el acta inicial.", "digital", True)], True)


def test_v8_uses_its_own_prompt_and_evidence_with_fake_model(tmp_path):
    class Fake:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            assert "v8 experimental" in prompt
            assert "tramo_id" in prompt
            return {"clausulas": [{
                "tramo_id": 1, "resumen": "La devolución depende del acta inicial.",
                "categoria": "devolucion", "responsable": "no_especificado",
                "uso_clasificador": "contexto", "confianza": 0.6,
            }]}

    model = Fake()
    path = tmp_path / "result.json"
    result = execute_reference_trial(SOURCE, model, path, metadata={}, evaluate=evaluate_v8_with_model)
    assert result["valid_clauses"][0]["texto_original"] == SOURCE.pages[0].text
    with pytest.raises(TrialAlreadyRecorded):
        execute_reference_trial(SOURCE, model, path, metadata={}, evaluate=evaluate_v8_with_model)
    assert model.calls == 1


def test_reference_trial_failure_records_only_safe_error(tmp_path):
    class Broken:
        calls = 0

        def invoke(self, _prompt):
            self.calls += 1
            raise RuntimeError("mensaje privado")

    path = tmp_path / "result.json"
    model = Broken()
    with pytest.raises(RuntimeError):
        execute_reference_trial(SOURCE, model, path, metadata={}, evaluate=evaluate_v8_with_model)
    text = path.read_text(encoding="utf-8")
    assert "mensaje privado" not in text
    assert json.loads(text)["state"] == "failed"
    assert model.calls == 1
