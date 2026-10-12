"""HU15 automático con PostgreSQL descartable y modelo simulado."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.db.provider_candidates_jobs import SqlAlchemyProviderCandidatesJobs
from app.services.provider_candidates_worker import ProviderCandidatesWorker
from tests.test_provider_candidates_postgres import ready_case, provider, command, execute
from tests.test_responsible_actor_postgres import MIGRATIONS, claim_case, local_engine, snapshot

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.")


@pytest.fixture
def automatic_case(ready_case):
    db, repo, claim, actor, specialty = ready_case
    with db.connect() as c:
        cursor = c.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / "20261011160000_hu15_busqueda_automatica.sql").read_text(encoding="utf-8"))
            c.commit()
        finally:
            cursor.close()
    with db.begin() as c:
        # No autorización, gasto ni responsable: búsqueda desde el reclamo.
        c.execute(text("DELETE FROM reclamo_responsables WHERE reclamo_id=:id"), {"id": claim})
        c.execute(text("UPDATE reclamos SET estado='Recibido',tipo_gasto=null,tipo_id=null WHERE id=:id"), {"id": claim})
    return ready_case, SqlAlchemyProviderCandidatesJobs(repo)


class Resolver:
    def __init__(self, specialty):
        self.specialty = specialty
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return {"especialidad_id": str(self.specialty), "fundamento": "Especialidad sintética.", "evidencia": "Descripción sintética"}


def task(case):
    data, _ = case
    with data[0].connect() as c:
        return c.execute(text("SELECT * FROM reclamo_tareas_proveedores WHERE reclamo_id=:id"),
                         {"id": data[2]}).mappings().one()


def test_worker_end_to_end_from_received_claim_and_no_infinite_loop(automatic_case):
    case, jobs = automatic_case
    db, repo, claim, _, specialty = case
    candidates = {provider(case), provider(case, area="Centro")}
    provider(case, city="Otra localidad")
    before = snapshot(db, claim)
    model = Resolver(specialty)
    worker = ProviderCandidatesWorker(jobs, resolver=model)
    assert worker.process_one()
    view = repo.get(claim)
    assert view.estado == "Recibido" and view.tipo_gasto is None
    assert view.tarea_agente == "completada" and set(p.id for p in view.candidatos) == candidates
    assert view.historial_busquedas[0].origen == "agente"
    assert view.historial_busquedas[0].usuario_id is None
    assert view.especialidad.id == specialty and model.calls == 1
    assert worker.process_one() is False and model.calls == 1 and view.historial_total == 1
    after = snapshot(db, claim)
    for table in ("reclamo_responsables", "reclamo_historial_estados", "notificaciones"):
        assert after[table] == before[table]
    for field in ('tipo_gasto','confianza_clasificacion','fundamento_clasificacion','estado'):
        assert after['reclamos'][0][field] == before['reclamos'][0][field]


def test_registered_specialty_works_with_external_permission_disabled(automatic_case):
    case, jobs = automatic_case
    with case[0].begin() as c:
        c.execute(text("UPDATE reclamos SET tipo_id=:s WHERE id=:id"), {"id": case[2], "s": case[-1]})
    provider(case)
    assert ProviderCandidatesWorker(jobs, external_enabled=False).process_one()
    assert task(automatic_case)["fuente"] == "registrada"
    assert task(automatic_case)["modelo"] is None


@pytest.mark.parametrize("failure", ["disabled", "ambiguous", "invalid", "503", "no_candidates"])
def test_failure_persists_review_and_deduplicated_notice_without_retry(automatic_case, failure):
    case, jobs = automatic_case
    resolver = Resolver(case[-1])
    if failure == 'ambiguous':
        resolver.invoke = lambda prompt: {"especialidad_id": None, "fundamento": "Ambiguo.", "evidencia": ""}
    if failure == 'invalid':
        resolver.specialty = uuid4()
    if failure == '503':
        def failed(prompt):
            raise RuntimeError('503 synthetic')
        resolver.invoke = failed
    worker = ProviderCandidatesWorker(jobs, resolver=None if failure == 'disabled' else resolver, external_enabled=False)
    assert worker.process_one()
    view = case[1].get(case[2])
    assert view.tarea_agente == 'revision' and view.aviso_operador == 'encolado'
    assert view.historial_total == 1
    assert worker.process_one() is False
    with case[0].connect() as c:
        assert c.execute(text("SELECT count(*) FROM notificaciones WHERE reclamo_id=:id AND clave_idempotencia LIKE '%:candidatos:%'"),
                         {'id': case[2]}).scalar_one() == 1


@pytest.mark.parametrize("change", ['description', 'location', 'manual_specialty', 'closed'])
def test_late_model_response_cannot_overwrite_changed_inputs_or_closed_claim(automatic_case, change):
    case, jobs = automatic_case
    jobs.discover()
    job = jobs.reserve_one()
    with case[0].begin() as c:
        if change == 'description':
            c.execute(text("UPDATE reclamos SET descripcion='Otro problema sintético' WHERE id=:id"), {'id': case[2]})
        elif change == 'location':
            c.execute(text("UPDATE propiedades SET localidad='Otra localidad' WHERE id=(SELECT propiedad_id FROM reclamos WHERE id=:id)"), {'id': case[2]})
        elif change == 'manual_specialty':
            execute(case, command(case[1],case[2],case[-1]))
        else:
            c.execute(text("UPDATE reclamos SET estado='Resuelto' WHERE id=:id"), {'id': case[2]})
    before = snapshot(case[0], case[2])
    assert jobs.finish(job, {'especialidad_id': case[-1], 'fuente': 'modelo', 'motivo': 'Respuesta tardía.'}) is None
    assert snapshot(case[0], case[2]) == before and task(automatic_case)['estado'] == 'cancelada'
    assert jobs.discover() == (0 if change == 'closed' else 1)


def test_two_workers_do_not_make_duplicate_model_calls(automatic_case):
    case, jobs = automatic_case
    entered, release = Event(), Event()
    class SlowResolver(Resolver):
        def invoke(self, prompt):
            entered.set()
            assert release.wait(timeout=5)
            return super().invoke(prompt)
    model = SlowResolver(case[-1])
    worker = ProviderCandidatesWorker(jobs,resolver=model)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(worker.process_one)
        assert entered.wait(timeout=5)
        assert pool.submit(worker.process_one).result(timeout=3) is False
        release.set()
        assert first.result(timeout=5)
    assert model.calls == 1 and case[1].get(case[2]).historial_total == 1


def test_expired_lease_is_reviewed_not_retried_and_old_result_discarded(automatic_case):
    case, jobs = automatic_case
    jobs.discover()
    job = jobs.reserve_one()
    with case[0].begin() as c:
        c.execute(text("UPDATE reclamo_tareas_proveedores SET reserva_hasta=clock_timestamp()-interval '1 second' WHERE reclamo_id=:id"), {'id': case[2]})
    assert not jobs.renew(job)
    assert jobs.finish(job, {'especialidad_id': case[-1], 'fuente': 'modelo', 'motivo': 'Tardío'}) is None
    jobs.discover()
    assert jobs.reserve_one() is None and task(automatic_case)['estado'] == 'revision'
    assert case[1].get(case[2]).historial_total == 0


def test_fresh_lease_renewal_and_same_inputs_never_regenerate_job(automatic_case):
    case, jobs = automatic_case
    jobs.discover()
    job = jobs.reserve_one()
    with case[0].begin() as c:
        c.execute(text("UPDATE reclamos SET estado='Autorizado',updated_at=clock_timestamp() WHERE id=:id"), {'id': case[2]})
    assert jobs.discover() == 0 and jobs.renew(job)
    assert jobs.finish(job, {'especialidad_id': case[-1], 'fuente': 'registrada', 'motivo': 'Registrada'}) is not None
    assert jobs.discover() == 0 and jobs.reserve_one() is None


def test_incremental_migration_security_and_base_audit_preserved(automatic_case):
    case, jobs = automatic_case
    execute(case, command(case[1],case[2],case[-1]))
    assert case[1].get(case[2]).historial_total == 1
    with case[0].connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='reclamo_tareas_proveedores'::regclass")).scalar_one()
        for role in ('anon','authenticated'):
            assert not c.execute(text("SELECT has_table_privilege(:role,'reclamo_tareas_proveedores','SELECT,INSERT,UPDATE,DELETE')"), {'role': role}).scalar_one()


def test_worker_rollback_does_not_mark_failed_audit_as_completed(automatic_case):
    case, jobs = automatic_case
    before = snapshot(case[0],case[2])
    def fail(conn,cursor,statement,parameters,context,many):
        if 'INSERT INTO reclamo_busquedas_proveedores' in statement:
            raise RuntimeError('Fallo sintético de auditoría.')
    event.listen(case[0],'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError):
            ProviderCandidatesWorker(jobs,resolver=Resolver(case[-1])).process_one()
    finally:
        event.remove(case[0],'before_cursor_execute',fail)
    assert snapshot(case[0],case[2]) == before
    assert task(automatic_case)['estado'] == 'procesando'
    assert case[1].get(case[2]).historial_total == 0


def test_specialty_removed_during_model_call_requests_review(automatic_case):
    case, jobs = automatic_case
    jobs.discover()
    job = jobs.reserve_one()
    with case[0].begin() as c:
        c.execute(text('DELETE FROM especialidades WHERE id=:id'), {'id': case[-1]})
    result = jobs.finish(job, {'especialidad_id': case[-1], 'fuente': 'modelo', 'motivo': 'Se había identificado.'})
    assert result.resultado == 'especialidad_pendiente'
    assert task(automatic_case)['estado'] == 'revision'


def test_qa_scope_does_not_discover_reserve_or_recover_another_claim(automatic_case):
    case, all_jobs = automatic_case
    db, repo, claim, _, specialty = case
    other, other_property, other_tenant = uuid4(), uuid4(), uuid4()
    with db.begin() as c:
        c.execute(text("""
            INSERT INTO propiedades (id,direccion,provincia,localidad,barrio,tipo,propietario_id)
            SELECT :property,'Otra unidad ficticia',p.provincia,p.localidad,p.barrio,p.tipo,p.propietario_id
            FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id WHERE r.id=:id
        """), {"property": other_property, "id": claim})
        c.execute(text("""
            INSERT INTO inquilinos (id,nombre_completo,dni,email,telefono,propiedad_id)
            VALUES (:tenant,'Otro Inquilino Sintetico','10000003','other-tenant@example.com','00000000',:property)
        """), {"tenant": other_tenant, "property": other_property})
        c.execute(text("""
            INSERT INTO reclamos (id,descripcion,urgencia,inquilino_id,propiedad_id)
            SELECT :other,descripcion,urgencia,:tenant,:property FROM reclamos WHERE id=:id
        """), {"other": other, "id": claim, "tenant": other_tenant, "property": other_property})
    scoped = SqlAlchemyProviderCandidatesJobs(repo, scope_claim_id=claim)
    assert scoped.discover() == 1
    with db.connect() as c:
        assert c.execute(text("SELECT reclamo_id FROM reclamo_tareas_proveedores")).scalars().all() == [claim]
    all_jobs.discover()
    other_jobs = SqlAlchemyProviderCandidatesJobs(repo, scope_claim_id=other)
    other_job = other_jobs.reserve_one()
    assert other_job['id'] == other
    with db.begin() as c:
        c.execute(text("UPDATE reclamo_tareas_proveedores SET reserva_hasta=clock_timestamp()-interval '1 second' WHERE reclamo_id=:id"),
                  {'id': other})
    assert ProviderCandidatesWorker(scoped, resolver=Resolver(specialty)).process_one()
    assert not scoped.reserve_one()
    with db.connect() as c:
        assert c.execute(text("SELECT estado FROM reclamo_tareas_proveedores WHERE reclamo_id=:id"),
                         {'id': other}).scalar_one() == 'procesando'
