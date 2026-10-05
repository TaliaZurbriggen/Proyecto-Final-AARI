"""Flujo asistido y literal, sin consumir APIs ni modificar la base compartida."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.db.clausulas_contrato import AnalysisJob, SqlAlchemyContractClausesRepository
from app.schemas.clausulas_contrato import ClauseReviewRequest
from app.schemas.analisis_asistido import AssistedReviewRequest, ContractAnalysisRequest
from app.services import contract_clause_assisted as assisted
from app.services.contract_clause_service import ContractClauseService
from app.services.contract_errors import ContractError
from app.services.contract_text_extraction import ContractText, PageText
from tests.test_contract_clause_activation import FakeSession, FakeSessionFactory


def uid(number):
    return UUID(f"00000000-0000-0000-0000-{number:012d}")


def source():
    return ContractText([
        PageText(1, "PREÁMBULO DEL CONTRATO\nQUINTA: El locador conserva", "digital", True),
        PageText(2, "la aptitud para el uso durante su vigencia.\nSEXTA: Debe avisarse el daño.", "digital", True),
    ], True)


def proposal(tramo_id=1):
    return {"tramo_id": tramo_id, "titulo": "Conservación", "resumen": "Propuesta pendiente.",
            "categoria": "reparacion", "responsable": "propietario", "uso_clasificador": "operativa",
            "confianza": 0.9, "condiciones": "Durante la vigencia.", "referencias": []}


def test_literal_conserves_preamble_cross_page_clauses_and_assigns_no_responsibility():
    clauses = assisted.literal_clauses(source())
    assert len(clauses) == 3
    fifth = next(item for item in clauses if item.numero == "5")
    assert fifth.paginas == [1, 2]
    assert "aptitud para el uso" in fifth.texto_original
    assert all(item.responsable == "no_especificado" and item.confianza == 0
               and item.resumen == assisted.LITERAL_SUMMARY and item.uso_clasificador == "contexto"
               for item in clauses)
    assert any("PREÁMBULO" in item.texto_original for item in clauses)


def test_literal_keeps_unrecognized_and_partial_text_without_joining_a_gap():
    text = ContractText([PageText(1, "PRIMERA: Inicio legible.", "digital", True),
                         PageText(2, "texto parcial", "sin_lectura", False),
                         PageText(3, "continuación sin encabezado", "digital", True)], False)
    clauses = assisted.literal_clauses(text)
    assert any(item.paginas == [2] and item.texto_original == "texto parcial" for item in clauses)
    assert not any(item.paginas == [1, 3] for item in clauses)
    assert any(item.numero is None for item in clauses)


def test_literal_splits_large_source_explicitly_without_losing_words():
    text = "PRIMERA: " + "contenido " * 1800
    clauses = assisted.literal_clauses(ContractText([PageText(1, text, "digital", True)], True))
    assert len(clauses) > 1
    assert all(len(item.texto_original) <= 8000 for item in clauses)
    assert "".join(item.texto_original for item in clauses).replace(" ", "") == text.replace(" ", "")
    assert all("parte" in item.titulo for item in clauses)


def test_json_interpretation_materializes_only_existing_full_source():
    model = Mock()
    model.invoke.return_value = json.dumps({"clausulas": [proposal(), proposal(999)]})
    accepted, rejected, incidents = assisted.interpret(source(), model)
    assert len(accepted) == 1 and accepted[0].paginas == [1, 2]
    assert accepted[0].texto_original.startswith("QUINTA:")
    assert rejected[0]["propuesta"]["tramo_id"] == 999 and incidents
    prompt = model.invoke.call_args.args[0]
    assert "SEXTA:" in prompt and "ESQUEMA DE SALIDA" in prompt
    assert model.invoke.call_count == 1


@pytest.mark.parametrize("response", ["no json", "{}", '{"clausulas": [{"tramo_id": "1"}]}',
                                      '{"clausulas": [], "inventado": true}'])
def test_invalid_json_cannot_become_a_valid_empty_analysis(response):
    with pytest.raises((ValueError, ValidationError)):
        assisted.interpret(source(), SimpleNamespace(invoke=lambda _: response))


def test_output_guidance_matches_the_successful_diagnostic_schema():
    from scripts.diagnose_contract_direct_gemini import native_schema
    assert assisted.output_schema() == native_schema()


def test_sdk_json_mode_no_native_schema_tools_or_hidden_retry(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.models = SimpleNamespace(generate_content=self.generate)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def generate(self, **kwargs):
            seen["generate"] = kwargs
            return SimpleNamespace(text='{"clausulas": []}')

    monkeypatch.setattr(assisted.genai, "Client", Client)
    model = assisted.JsonClauseModel("synthetic-test-key", assisted.DEFAULT_MODEL)
    assert model.invoke("texto sintético") == '{"clausulas": []}'
    assert seen["http_options"].retry_options.attempts == 1
    config = seen["generate"]["config"]
    assert config.response_mime_type == "application/json" and config.response_json_schema is None
    assert not config.tools
    guard = seen["http_options"].client_args["event_hooks"]["request"][0]
    request = SimpleNamespace(method="POST", url=SimpleNamespace(
        host="generativelanguage.googleapis.com", path=f"/v1beta/models/{assisted.DEFAULT_MODEL}:generateContent"))
    guard(request)
    with pytest.raises(RuntimeError, match="reintento"):
        guard(request)


def test_external_flag_and_key_are_checked_without_any_request(monkeypatch):
    monkeypatch.delenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="deshabilitado"):
        assisted.get_assisted_model()
    monkeypatch.setenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="configurado"):
        assisted.get_assisted_model()


def service_for(monkeypatch, mode, extracted=None, error=None):
    repository = Mock()
    job = AnalysisJob(uid(1), uid(2), uid(3), "private/synthetic.pdf", 1, mode, uid(4))
    repository.claim_due.side_effect = [[job], []]
    repository.renew_lease.return_value = True
    model = Mock()
    model.invoke.side_effect = error
    model.invoke.return_value = {"clausulas": [proposal()]}
    factory = Mock(return_value=model)
    monkeypatch.setattr("app.services.contract_clause_service.extract_contract_text",
                        lambda *_: extracted or source())
    service = ContractClauseService(repository, SimpleNamespace(download=lambda _: b"synthetic"),
                                    model_factory=factory)
    return service, repository, factory, model


def test_literal_service_never_constructs_a_model_even_when_disabled(monkeypatch):
    monkeypatch.delenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", raising=False)
    service, repository, factory, model = service_for(monkeypatch, "literal")
    assert service.process_due() == 1
    factory.assert_not_called()
    model.invoke.assert_not_called()
    result = repository.complete.call_args.kwargs
    assert result["origins"] == ["literal"] * 3
    assert result["execution_id"] == uid(4)


def test_assisted_service_keeps_unselected_source_as_literal(monkeypatch):
    service, repository, _, model = service_for(monkeypatch, "ia")
    service.process_due()
    result = repository.complete.call_args.kwargs
    assert len(result["clauses"]) == 3 and result["origins"] == ["ia", "literal", "literal"]
    assert model.invoke.call_count == 1
    repository.fail.assert_not_called()


def test_provider_error_is_safe_terminal_and_keeps_the_contract(monkeypatch, caplog):
    service, repository, _, model = service_for(monkeypatch, "ia", error=Exception("SECRET PRIVATE CONTENT"))
    service.process_due()
    model.invoke.assert_called_once()
    repository.complete.assert_not_called()
    assert "SECRET" not in str(repository.fail.call_args) + caplog.text
    assert repository.fail.call_args.kwargs["execution_id"] == uid(4)


def test_partial_reading_does_not_send_partial_contract_to_gemini(monkeypatch):
    partial = ContractText([PageText(1, "PRIMERA: texto", "digital", True),
                            PageText(2, "", "sin_lectura", False)], False)
    service, repository, _, model = service_for(monkeypatch, "ia", partial)
    service.process_due()
    model.invoke.assert_not_called()
    repository.fail.assert_called_once()


@pytest.mark.parametrize("role", ["inquilino", "propietario", "operador"])
def test_literal_request_rejects_non_admins(role):
    with pytest.raises(ContractError) as error:
        ContractClauseService(None, None).request(uid(1), uid(2),
            SimpleNamespace(rol=role, primer_ingreso=False), mode="literal")
    assert error.value.status == 403


def test_only_declared_analysis_modes_are_valid():
    assert ContractAnalysisRequest().modo == "ia"
    with pytest.raises(ValidationError):
        ContractAnalysisRequest(modo="otro")


@pytest.mark.parametrize("summary", [" ", "\n\t"])
def test_manual_summary_cannot_be_only_whitespace(summary):
    with pytest.raises(ValidationError):
        AssistedReviewRequest(accion="editar", revision=1, resumen=summary)


def test_manual_review_trims_summary_and_conditions():
    review = AssistedReviewRequest(accion="editar", revision=1,
                                  resumen="  Texto revisado.  ", condiciones="  Durante la vigencia.  ")
    assert review.resumen == "Texto revisado."
    assert review.condiciones == "Durante la vigencia."


def test_literal_placeholder_cannot_be_enabled_as_a_rule():
    row = {"revision": 1, "resumen": assisted.LITERAL_SUMMARY, "categoria": "otro",
           "responsable": "no_especificado", "condiciones": None, "origen": "literal",
           "uso_clasificador": "contexto", "estado_revision": "pendiente", "paginas": [1],
           "referencias": [], "analisis_id": uid(1)}
    session = FakeSession(row)
    repository = SqlAlchemyContractClausesRepository(FakeSessionFactory(session))
    with pytest.raises(ContractError) as error:
        repository.review(uid(1), uid(2), ClauseReviewRequest(
            accion="editar", revision=1, uso_clasificador="operativa"), uid(3))
    assert error.value.status == 422
    assert not any("UPDATE contrato_clausulas" in sql for sql, _ in session.calls)


def test_additive_migration_protects_attempt_history():
    sql = (Path(__file__).parents[1] / "migrations/25_extraccion_asistida_literal.sql").read_text().lower()
    assert "contrato_analisis_intentos enable row level security" in sql
    assert "from public, anon, authenticated" in sql
    assert "drop table" not in sql and "delete from" not in sql


def test_previous_prompt_job_is_not_sent_as_a_new_prompt(monkeypatch):
    service, repository, _, model = service_for(monkeypatch, "ia")
    repository.claim_due.side_effect = [[AnalysisJob(uid(1), uid(2), uid(3),
        "private/synthetic.pdf", 1, "ia", uid(4), "fake", "v4")], []]
    service.process_due()
    model.invoke.assert_not_called()
    repository.fail.assert_called_once()
    assert "versión anterior" in repository.fail.call_args.args[2]


def test_api_uses_declared_mode_and_rejects_an_unknown_mode():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.contratos import contract_user, get_contract_clause_service

    repository = Mock()
    repository.get.return_value = {"id": uid(3), "contrato_id": uid(1), "documento_id": uid(2),
        "estado": "pendiente", "modo": "literal", "completo": False, "intentos": 0,
        "created_at": "2026-10-05T12:00:00Z", "updated_at": "2026-10-05T12:00:00Z"}
    service = ContractClauseService(repository, None)
    actor = SimpleNamespace(id=uid(4), rol="administrador", primer_ingreso=False)
    app.dependency_overrides[contract_user] = lambda: actor
    app.dependency_overrides[get_contract_clause_service] = lambda: service
    try:
        client = TestClient(app)
        endpoint = f"/contratos/{uid(1)}/documentos/{uid(2)}/analisis"
        assert client.post(endpoint, json={"modo": "literal"}).status_code == 202
        assert repository.request_analysis.call_args.kwargs["model"] == "local"
        assert repository.request_analysis.call_args.kwargs["mode"] == "literal"
        assert client.post(endpoint, json={"modo": "otro"}).status_code == 422
        actor.rol = "inquilino"
        assert client.post(endpoint, json={"modo": "literal"}).status_code == 403
    finally:
        app.dependency_overrides.pop(contract_user, None)
        app.dependency_overrides.pop(get_contract_clause_service, None)
