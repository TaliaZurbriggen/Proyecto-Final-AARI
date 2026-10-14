"""QA externo autorizado: sólo reclamos propios y rollback; Gemini simulado."""

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.db.provider_candidates_jobs import SqlAlchemyProviderCandidatesJobs
from app.services.provider_candidates_worker import ProviderCandidatesWorker
from tests.test_provider_candidates_supabase_integration import case, provider, snapshot

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_HU15_AUTOMATIC_SUPABASE_INTEGRATION") != "1",
    reason="Requiere autorización de la migración automática y QA aislado en Supabase.",
)


def jobs_for(case):
    identifier = case.claims[0]
    case.connection.execute(text("""
        UPDATE reclamos SET estado='Recibido',tipo_id=null,tipo_gasto=null
        WHERE id=:id
    """), {"id": identifier})
    case.connection.execute(text("DELETE FROM reclamo_responsables WHERE reclamo_id=:id"), {"id": identifier})
    return SqlAlchemyProviderCandidatesJobs(case.repo, scope_claim_id=identifier)


def test_agent_from_received_without_expense_or_responsible_is_isolated(case):
    expected = {provider(case), provider(case, area="Centro")}
    provider(case, city=case.cities[1])
    provider(case, active=False)
    jobs = jobs_for(case)
    before = snapshot(case)
    calls = []
    def resolve(prompt):
        calls.append(prompt)
        return {"especialidad_id": case.specialty, "fundamento": "Resolución sintética.",
                "evidencia": "reparación de prueba"}
    worker = ProviderCandidatesWorker(jobs, resolver=SimpleNamespace(invoke=resolve), heartbeat_seconds=300)
    assert worker.process_one()
    assert not worker.process_one() and len(calls) == 1
    result = case.repo.get(case.claims[0])
    assert result.tarea_agente == "completada"
    assert {item.id for item in result.candidatos} == expected
    assert result.historial_busquedas[0].origen == "agente"
    after = snapshot(case)
    for key in ("estado", "tipo_gasto", "fundamento_clasificacion", "confianza_clasificacion"):
        assert after["reclamos"][0][key] == before["reclamos"][0][key]
    assert after["reclamo_responsables"] == before["reclamo_responsables"] == []
    assert after["reclamo_historial_estados"] == before["reclamo_historial_estados"]
    # El segundo reclamo del mismo fixture no fue ni descubierto ni reservado.
    assert case.connection.execute(text("SELECT reclamo_id FROM reclamo_tareas_proveedores WHERE reclamo_id IN (:first,:second)"),
                                   {"first": case.claims[0], "second": case.claims[1]}).scalars().all() == [case.claims[0]]


@pytest.mark.parametrize("mode", ["disabled", "ambiguous", "unavailable"])
def test_uncertain_or_unavailable_goes_to_review_without_automatic_retry(case, mode):
    jobs = jobs_for(case)
    calls = []
    def resolve(prompt):
        calls.append(prompt)
        if mode == "unavailable":
            raise RuntimeError("503 sintético, sin datos externos.")
        return {"especialidad_id": None, "fundamento": "Insuficiente.", "evidencia": ""}
    worker = ProviderCandidatesWorker(jobs, resolver=None if mode == "disabled" else SimpleNamespace(invoke=resolve),
                                     external_enabled=False, heartbeat_seconds=300)
    assert worker.process_one()
    assert not worker.process_one()
    assert len(calls) == (0 if mode == "disabled" else 1)
    view = case.repo.get(case.claims[0])
    assert view.tarea_agente == "revision" and view.historial_total == 1
    assert view.especialidad is None
    alerts = case.connection.execute(text("""
        SELECT estado_envio FROM notificaciones WHERE reclamo_id=:id
            AND clave_idempotencia LIKE '%:candidatos:%'
    """), {"id": case.claims[0]}).scalars().all()
    assert alerts == ["pendiente"]  # Se encola; no se envía un correo en QA.
