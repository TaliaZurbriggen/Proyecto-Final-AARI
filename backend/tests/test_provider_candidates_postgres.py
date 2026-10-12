"""HU15 sobre PostgreSQL local descartable; nunca Supabase ni servicios externos."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.db.provider_candidates import SqlAlchemyProviderCandidatesRepository
from app.db.proveedores import SqlAlchemyProveedoresRepository
from app.schemas.provider_candidates import CandidateSearchRequest
from app.services.provider_candidates_service import (
    CandidateSearchConflictError, CandidateSearchPermissionError, CandidateSpecialtyNotFoundError,
)
from tests.test_responsible_actor_postgres import (
    MIGRATIONS, claim_case, classification, local_engine, snapshot,
)

pytestmark = pytest.mark.skipif(not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.")


@pytest.fixture
def ready_case(claim_case):
    db, claims, claim = claim_case
    with db.connect() as c:
        cursor = c.connection.cursor()
        try:
            cursor.execute((MIGRATIONS / "20261009120000_hu15_proveedores_candidatos.sql").read_text(encoding="utf-8"))
            c.commit()
        finally:
            cursor.close()
    claims.persist_classification(claim, classification("ordinario"))
    with db.begin() as c:
        actor = c.execute(text("UPDATE usuarios SET primer_ingreso=false WHERE rol='operador' RETURNING id")).scalar_one()
        # La búsqueda es preliminar: este estado es sólo una variante de fixture.
        c.execute(text("UPDATE reclamos SET estado='Pendiente de asignación' WHERE id=:id"), {"id": claim})
        specialty = c.execute(text("INSERT INTO especialidades (nombre) VALUES ('Especialidad Sintetica HU15') RETURNING id")).scalar_one()
        c.execute(text("UPDATE propiedades SET barrio='Centro' WHERE id=(SELECT propiedad_id FROM reclamos WHERE id=:id)"), {"id": claim})
    repo = SqlAlchemyProviderCandidatesRepository(claims.session_factory)
    return db, repo, claim, actor, specialty


def command(repo, claim, specialty=None, request_id=None):
    return CandidateSearchRequest(
        request_id=request_id or uuid4(), expected_updated_at=repo.get(claim).updated_at,
        especialidad_id=specialty,
    )


def execute(case, request):
    _, repo, claim, actor, _ = case
    return repo.search(claim, request, origin="operador", user_id=actor)


def provider(case, *, city="Localidad de prueba", province="Córdoba", area=None, active=True):
    db, _, _, _, specialty = case
    with db.begin() as c:
        id = c.execute(text("""
            INSERT INTO proveedores (nombre_razon_social, telefono, activo)
            VALUES ('Proveedor Sintetico HU15', :phone, :active) RETURNING id
        """), {"phone": "+54" + str(uuid4().int)[:12], "active": active}).scalar_one()
        c.execute(text("INSERT INTO proveedor_especialidades VALUES (:p,:s)"), {"p": id, "s": specialty})
        coverage = c.execute(text("""
            INSERT INTO proveedor_coberturas (proveedor_id, provincia, localidad, cubre_toda_localidad)
            VALUES (:id,:p,:c,:all) RETURNING id
        """), {"id": id, "p": province, "c": city, "all": area is None}).scalar_one()
        if area:
            c.execute(text("INSERT INTO proveedor_cobertura_barrios (cobertura_id,barrio) VALUES (:id,:area)"),
                      {"id": coverage, "area": area})
    return id


def test_read_only_then_save_specialty_and_candidates_without_reclassifying(ready_case):
    db, repo, claim, actor, specialty = ready_case
    expected = {provider(ready_case), provider(ready_case, area="Centro")}
    provider(ready_case, city="Otra localidad")
    provider(ready_case, area="Centro Norte")
    provider(ready_case, active=False)
    before = snapshot(db, claim)
    assert repo.get(claim).resultado == "especialidad_pendiente"
    assert repo.list().total == 1
    assert snapshot(db, claim) == before
    saved = execute(ready_case, command(repo, claim, specialty))
    assert set(saved.candidato_ids) == expected and saved.aviso_operador == "no_aplica"
    detail = repo.get(claim, page_size=1)
    assert detail.total == 2 and detail.total_pages == 2 and len(detail.candidatos) == 1
    assert detail.especialidad.id == specialty and detail.historial_total == 1
    after = snapshot(db, claim)
    for key in ("tipo_gasto", "fundamento_clasificacion", "actor_responsable", "confianza_clasificacion", "estado"):
        if key in before["reclamos"][0]:
            assert after["reclamos"][0][key] == before["reclamos"][0][key]
    assert after["reclamo_responsables"] == before["reclamo_responsables"]
    assert after["reclamo_historial_estados"] == before["reclamo_historial_estados"]
    assert after["notificaciones"] == before["notificaciones"]


def test_no_candidates_audited_and_alert_deduplicated(ready_case):
    _, repo, claim, _, specialty = ready_case
    first = command(repo, claim, specialty)
    saved = execute(ready_case, first)
    assert saved.resultado == "sin_candidatos" and saved.aviso_operador == "encolado"
    replay = execute(ready_case, first)
    assert replay.busqueda_id == saved.busqueda_id and replay.repetida
    execute(ready_case, command(repo, claim, specialty))
    assert repo.get(claim).historial_total == 2
    db = ready_case[0]
    with db.connect() as c:
        assert c.execute(text("SELECT count(*) FROM notificaciones WHERE reclamo_id=:id AND clave_idempotencia LIKE '%:candidatos:%'"), {"id": claim}).scalar_one() == 1
    different = first.model_copy(update={"especialidad_id": None})
    with pytest.raises(CandidateSearchConflictError):
        execute(ready_case, different)


def test_read_snapshot_survives_concurrent_provider_deactivation(ready_case, monkeypatch):
    db, repo, claim, _, specialty = ready_case
    candidate = provider(ready_case)
    execute(ready_case, command(repo, claim, specialty))
    original = SqlAlchemyProveedoresRepository.candidate_records

    def deactivate_before_hydrating(session, ids):
        with db.begin() as c:
            c.execute(text("UPDATE proveedores SET activo=false WHERE id=:id"), {"id": candidate})
        return original(session, ids)

    monkeypatch.setattr(SqlAlchemyProveedoresRepository, "candidate_records", deactivate_before_hydrating)
    view = repo.get(claim)
    assert view.total == 1 and view.candidatos[0].activo
    # La siguiente lectura sí refleja la baja; no se usa un cache del padrón.
    monkeypatch.setattr(SqlAlchemyProveedoresRepository, "candidate_records", original)
    assert repo.get(claim).total == 0


def test_missing_specialty_alert_and_no_fake_recipient(ready_case):
    db, repo, claim, _, _ = ready_case
    result = execute(ready_case, command(repo, claim))
    assert result.resultado == "especialidad_pendiente"
    with db.begin() as c:
        c.execute(text("UPDATE usuarios SET activo=false WHERE rol='operador'"))
    result = repo.search(claim, command(repo, claim, ready_case[-1]), origin="agente", user_id=None)
    assert result.aviso_operador == "sin_destinatario"
    assert repo.get(claim).aviso_operador == "sin_destinatario"


@pytest.mark.parametrize("state", ["Autorizado", "Pendiente de respuesta del responsable", "Recibido"])
def test_search_preserves_pending_decisions(ready_case, state):
    db, repo, claim, _, specialty = ready_case
    with db.begin() as c:
        c.execute(text("UPDATE reclamos SET estado=:state WHERE id=:id"), {"state": state, "id": claim})
    before = snapshot(db, claim)
    assert repo.list().total == 1 and repo.get(claim).puede_buscar
    execute(ready_case, command(repo, claim, specialty))
    after = snapshot(db, claim)
    assert after['reclamos'][0]['estado'] == state
    for table in ('reclamo_responsables', 'reclamo_historial_estados'):
        assert after[table] == before[table]


def test_stale_version_unknown_specialty_and_inactive_actor_write_nothing(ready_case):
    db, repo, claim, actor, specialty = ready_case
    stale = command(repo, claim, specialty)
    execute(ready_case, command(repo, claim, specialty))
    before = snapshot(db, claim)
    with pytest.raises(CandidateSearchConflictError):
        execute(ready_case, stale)
    with pytest.raises(CandidateSpecialtyNotFoundError):
        execute(ready_case, command(repo, claim, uuid4()))
    assert snapshot(db, claim) == before
    with db.begin() as c:
        c.execute(text("UPDATE usuarios SET primer_ingreso=true WHERE id=:id"), {"id": actor})
    with pytest.raises(CandidateSearchPermissionError):
        execute(ready_case, command(repo, claim, specialty))


@pytest.mark.parametrize("same_id", [False, True])
def test_parallel_requests_one_write_or_safe_replay(ready_case, same_id):
    _, repo, claim, _, specialty = ready_case
    first = command(repo, claim, specialty)
    second = first if same_id else first.model_copy(update={"request_id": uuid4()})
    barrier = Barrier(2)
    def run(request):
        barrier.wait(timeout=5)
        try:
            return execute(ready_case, request)
        except CandidateSearchConflictError:
            return None
    with ThreadPoolExecutor(2) as threads:
        results = list(threads.map(run, [first, second]))
    assert repo.get(claim).historial_total == 1
    if same_id:
        assert {item.repetida for item in results} == {False, True}
    else:
        assert sum(item is not None for item in results) == 1


def test_atomic_rollback_of_specialty_outbox_and_audit(ready_case):
    db, repo, claim, _, specialty = ready_case
    request = command(repo, claim, specialty)
    before = snapshot(db, claim)
    def fail(conn, cursor, statement, parameters, context, many):
        if "INSERT INTO reclamo_busquedas_proveedores" in statement:
            raise RuntimeError("Fallo sintético de auditoría.")
    event.listen(db, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            execute(ready_case, request)
    finally:
        event.remove(db, "before_cursor_execute", fail)
    assert snapshot(db, claim) == before and repo.get(claim).historial_total == 0


def test_audit_rls_and_no_public_grants(ready_case):
    db, repo, claim, _, _ = ready_case
    execute(ready_case, command(repo, claim))
    with db.connect() as c:
        assert c.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid='reclamo_busquedas_proveedores'::regclass")).scalar_one()
        for role in ("anon", "authenticated"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert not c.execute(text("SELECT has_table_privilege(:role, 'reclamo_busquedas_proveedores', :privilege)"),
                                     {"role": role, "privilege": privilege}).scalar_one()
        with pytest.raises(Exception):
            c.execute(text("SET LOCAL ROLE anon"))
            c.execute(text("SELECT * FROM reclamo_busquedas_proveedores"))
