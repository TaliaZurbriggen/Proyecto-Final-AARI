"""La IA no habilita reglas contractuales sin una edición explícita."""

import json
from uuid import UUID

import pytest

from app.db.clausulas_contrato import SqlAlchemyContractClausesRepository
from app.schemas.clausulas_contrato import ClauseReviewRequest, ExtractedClause


def uid(number):
    return UUID(f"00000000-0000-0000-0000-{number:012d}")


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row

    def all(self):
        return []


class FakeSession:
    def __init__(self, review_row=None):
        self.review_row = review_row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params or {}))
        if "SELECT estado, ejecucion_id FROM contrato_analisis" in sql:
            return FakeResult({"estado": "procesando"})
        if "SELECT cl.*, a.contrato_id" in sql:
            return FakeResult(self.review_row)
        return FakeResult()


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def begin(self):
        return self.session

    def __call__(self):
        return self.session


def call_with(session, fragment):
    return next((sql, params) for sql, params in session.calls if fragment in sql)


def test_model_proposal_is_saved_as_context_without_losing_original_usage():
    session = FakeSession()
    repository = SqlAlchemyContractClausesRepository(FakeSessionFactory(session))
    proposal = ExtractedClause.model_validate({
        "numero": "SEXTA", "titulo": "Gastos",
        "evidencias": [{"pagina": 2, "texto": "SEXTA: Gastos sujetos a revisión."}],
        "resumen": "La atribución requiere revisión.",
        "categoria": "expensa", "responsable": "condicional",
        "uso_clasificador": "operativa", "condiciones": "Revisar la excepción.",
        "confianza": 0.9,
    })

    assert repository.complete(uid(1), pages=[], clauses=[proposal], rejected=[],
                               complete=True, incidents=[]) is True

    _, stored = call_with(session, "INSERT INTO contrato_clausulas")
    assert stored["uso_clasificador"] == "contexto"
    assert json.loads(stored["original"])["uso_clasificador"] == "operativa"
    assert not any("DELETE FROM contrato_clausulas" in sql for sql, _ in session.calls)


@pytest.mark.parametrize(
    ("payload", "expected_usage", "explicit_activation"),
    [
        (ClauseReviewRequest(accion="confirmar", revision=1), "contexto", False),
        (ClauseReviewRequest(accion="editar", revision=1, resumen="Revisado."), "contexto", False),
        (ClauseReviewRequest(accion="editar", revision=1, uso_clasificador="operativa"),
         "operativa", True),
    ],
)
def test_only_explicit_edit_can_enable_a_legacy_operational_proposal(
    payload, expected_usage, explicit_activation,
):
    row = {
        "revision": 1, "resumen": "Propuesta de la IA.", "categoria": "expensa",
        "responsable": "condicional", "condiciones": "Revisar excepción.",
        "uso_clasificador": "operativa", "estado_revision": "pendiente",
        "paginas": [2], "referencias": [], "analisis_id": uid(4),
    }
    session = FakeSession(row)
    repository = SqlAlchemyContractClausesRepository(FakeSessionFactory(session))
    repository.get = lambda *_args: {"clausulas": []}

    repository.review(uid(1), uid(2), payload, uid(3))

    _, update = call_with(session, "UPDATE contrato_clausulas")
    _, event = call_with(session, "INSERT INTO contrato_clausula_eventos")
    assert update["usage"] == expected_usage
    after = json.loads(event["after"])
    assert after.get("habilitacion_operativa_explicita", False) is explicit_activation


def test_claim_context_requires_the_explicit_activation_event():
    session = FakeSession()
    repository = SqlAlchemyContractClausesRepository(FakeSessionFactory(session))

    assert repository.confirmed_for_claim(uid(1)) == []

    sql, _ = call_with(session, "WITH applicable_contract")
    assert "cl.estado_revision='editada'" in sql
    assert "cl.uso_clasificador='operativa'" in sql
    assert "habilitacion_operativa_explicita" in sql
