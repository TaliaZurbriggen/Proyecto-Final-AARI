"""La evaluación fragmentada conserva páginas, evidencia y checkpoints."""

import json

import pytest
from google.genai.errors import ClientError

from app.schemas.clausulas_contrato import ExtractedClauseBatch
from app.services.contract_clause_corpus import ContractClauseCorpusError
from app.services.contract_clause_windows import (
    build_clause_windows, evaluate_clause_window, merge_clause_window_results,
)
from app.services.contract_text_extraction import PageText
from scripts.evaluate_contract_clause_windows import _provider_failure_metadata


PAGE_ONE = "El inquilino avisará cualquier pérdida de agua"
PAGE_TWO = "dentro de las veinticuatro horas de detectarla"
PAGE_THREE = "La inmobiliaria recibirá la comunicación del incidente"


def pages():
    return [
        PageText(index, text, "digital", True)
        for index, text in enumerate((PAGE_ONE, PAGE_TWO, PAGE_THREE), start=1)
    ]


def batch(evidences, *, summary="El inquilino debe avisar la pérdida de agua."):
    return ExtractedClauseBatch.model_validate({"clausulas": [{
        "numero": "SEGUNDA",
        "titulo": "Aviso",
        "evidencias": evidences,
        "resumen": summary,
        "categoria": "aviso",
        "responsable": "inquilino",
        "uso_clasificador": "operativa",
        "condiciones": "Dentro de las veinticuatro horas.",
        "referencias": [],
        "confianza": 0.9,
    }]})


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def evaluate(window, model, path):
    return evaluate_clause_window(
        window, model, document_id="V01", source_sha256="source-hash",
        prompt_version="v4", model_name="gemini-3.5-flash", result_path=path,
    )


def merge(windows, results):
    return merge_clause_window_results(
        windows, results, document_id="V01", source_sha256="source-hash",
        prompt_version="v4", model_name="gemini-3.5-flash",
    )


def test_windows_overlap_and_preserve_original_page_numbers():
    windows = build_clause_windows(pages())

    assert [window.page_numbers for window in windows] == [[1, 2], [2, 3]]
    assert "[PÁGINA 2]" in windows[0].model_text
    assert "[PÁGINA 2]" in windows[1].model_text
    assert "[PÁGINA 3]" not in windows[0].model_text
    assert [window.page_numbers for window in build_clause_windows(pages()[:1])] == [[1]]

    nine = [PageText(index, f"Página {index}", "digital", True) for index in range(1, 10)]
    assert [window.page_numbers for window in build_clause_windows(nine)] == [
        [index, index + 1] for index in range(1, 9)
    ]


def test_rejects_invalid_window_configuration_and_gapped_pages():
    with pytest.raises(ContractClauseCorpusError, match="configuración"):
        build_clause_windows(pages(), pages_per_window=2, overlap_pages=2)
    with pytest.raises(ContractClauseCorpusError, match="consecutivas"):
        build_clause_windows([pages()[0], pages()[2]])


def test_cross_page_evidence_is_anchored_to_original_pages(tmp_path):
    window = build_clause_windows(pages())[0]
    model = FakeModel(batch([
        {"pagina": 1, "texto": PAGE_ONE},
        {"pagina": 2, "texto": PAGE_TWO},
    ]))
    output = tmp_path / "ventana_01.json"

    result = evaluate(window, model, output)

    assert output.exists()
    assert "[PÁGINA 1]" in model.prompts[0]
    assert "[PÁGINA 2]" in model.prompts[0]
    assert result["valid_clauses"][0]["paginas"] == [1, 2]
    assert result["valid_clauses"][0]["evidencias"] == [
        {"pagina": 1, "texto": PAGE_ONE},
        {"pagina": 2, "texto": PAGE_TWO},
    ]
    assert result["rejected_proposals"] == []
    with pytest.raises(ContractClauseCorpusError, match="ya tiene resultado"):
        evaluate(window, model, output)
    assert len(model.prompts) == 1


def test_completed_window_survives_failure_and_exact_duplicate_is_removed(tmp_path):
    windows = build_clause_windows(pages())
    repeated = batch([{"pagina": 2, "texto": PAGE_TWO}])
    first = tmp_path / "ventana_01.json"
    second = tmp_path / "ventana_02.json"
    result_one = evaluate(windows[0], FakeModel(repeated), first)

    failed_model = FakeModel(RuntimeError("503"))
    with pytest.raises(RuntimeError, match="503"):
        evaluate(windows[1], failed_model, second)
    assert len(failed_model.prompts) == 1
    assert first.exists() and not second.exists()
    assert json.loads(first.read_text(encoding="utf-8")) == result_one

    result_two = evaluate(windows[1], FakeModel(repeated), second)
    combined = merge(windows, [result_one, result_two])

    assert combined["external_calls"] == 2
    assert combined["model_proposals"] == 2
    assert len(combined["valid_clauses"]) == 1
    assert combined["duplicate_proposals_removed"] == 1
    assert combined["provenance"] == [{"clause_ordinal": 1, "windows": [1, 2]}]


def test_different_interpretations_of_same_evidence_are_kept_for_review(tmp_path):
    windows = build_clause_windows(pages())
    evidence = [{"pagina": 2, "texto": PAGE_TWO}]
    first = evaluate(windows[0], FakeModel(batch(evidence)), tmp_path / "first.json")
    second = evaluate(
        windows[1], FakeModel(batch(evidence, summary="El aviso tiene un plazo de veinticuatro horas.")),
        tmp_path / "second.json",
    )

    combined = merge(windows, [first, second])

    assert len(combined["valid_clauses"]) == 2
    assert combined["duplicate_proposals_removed"] == 0
    assert combined["human_review_required"] is True


def test_assembly_rejects_missing_or_tampered_windows(tmp_path):
    windows = build_clause_windows(pages())
    result = evaluate(
        windows[0], FakeModel(batch([{"pagina": 2, "texto": PAGE_TWO}])),
        tmp_path / "first.json",
    )
    with pytest.raises(ContractClauseCorpusError, match="Faltan resultados"):
        merge(windows, [result])

    changed_hash = {**result, "source_sha256": "different"}
    with pytest.raises(ContractClauseCorpusError, match="no coincide"):
        merge(windows[:1], [changed_hash])

    changed_evidence = json.loads(json.dumps(result))
    changed_evidence["valid_clauses"][0]["evidencias"][0]["pagina"] = 3
    with pytest.raises(ContractClauseCorpusError, match="fuera de sus páginas"):
        merge(windows[:1], [changed_evidence])

    missing_call_count = {key: value for key, value in result.items() if key != "external_calls"}
    with pytest.raises(ContractClauseCorpusError, match="incompleto"):
        merge(windows[:1], [missing_call_count])

    malformed_incidents = {**result, "evidence_incidents": "texto no estructurado"}
    with pytest.raises(ContractClauseCorpusError, match="incompleto"):
        merge(windows[:1], [malformed_incidents])


def test_failure_log_keeps_quota_metadata_but_not_provider_message():
    provider = ClientError(429, {"error": {
        "status": "RESOURCE_EXHAUSTED",
        "message": "No registrar este texto ni datos privados",
        "details": [{
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{
                "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                "quotaValue": "20",
            }],
        }, {
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": "41s",
        }],
    }})
    wrapped = RuntimeError("Fallo del adaptador")
    wrapped.__cause__ = provider

    metadata = _provider_failure_metadata(wrapped)

    assert metadata == {
        "provider_status": 429,
        "provider_code": "RESOURCE_EXHAUSTED",
        "quota_metric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
        "quota_id": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        "quota_value": "20",
        "retry_delay": "41s",
    }
    assert "No registrar" not in json.dumps(metadata)
