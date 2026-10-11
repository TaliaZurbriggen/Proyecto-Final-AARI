"""QA HU15 autorizado: registros propios, transacción externa y rollback.

No modifica registros existentes, consume la secuencia de reclamos ni envía
correos. Las llamadas a Gemini, SMTP y Storage están prohibidas en estos tests.
"""

from contextlib import contextmanager
from datetime import timedelta
import os
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.auth import get_current_user
from app.api.provider_candidates import get_candidates_repository, router
from app.db.database import engine
from app.db.provider_candidates import SqlAlchemyProviderCandidatesRepository
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_candidates import CandidateSearchRequest
from app.schemas.reclamos import AgentClassificationResult
from app.services.provider_candidates_service import (
    CandidateSearchConflictError, CandidateSearchPermissionError,
    CandidateSpecialtyNotFoundError,
)

pytestmark = pytest.mark.skipif(os.getenv("RUN_HU15_SUPABASE_INTEGRATION") != "1",
                               reason="Requiere autorización HU15 en Supabase con rollback.")


class RollbackSession(Session):
    """La conexión externa del fixture ya fijó su aislamiento antes de begin.

    SQLAlchemy prohíbe fijarlo otra vez después de begin, aunque sea idéntico.
    Verificarlo, sin cambiar el aislamiento ni el repositorio de producción.
    """

    def connection(self, bind_arguments=None, execution_options=None):
        if execution_options:
            assert execution_options == {"isolation_level": "REPEATABLE READ"}
            assert self.get_bind().get_execution_options()["isolation_level"] == "REPEATABLE READ"
        return super().connection(bind_arguments=bind_arguments)


@contextmanager
def synthetic_context(db=engine):
    marker = uuid4().hex
    identities = []
    claim_ids = []
    with db.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL lock_timeout='5s'"))
            connection.execute(text("SET LOCAL statement_timeout='15s'"))
            users = {}
            for role in ("operador", "administrador"):
                identifier = uuid4()
                email = f"qa-hu15-{role}-{marker}@example.com"
                connection.execute(text("""
                    INSERT INTO usuarios (id, email, password_hash, rol, primer_ingreso, nombre_completo)
                    VALUES (:id, :email, 'not-a-credential', CAST(:role AS rol_usuario), false, :name)
                """), {"id": identifier, "email": email, "role": role,
                       "name": "Operador Sintetico" if role == "operador" else None})
                identities.append(("usuarios", identifier))
                users[role] = AuthenticatedUser(id=identifier, email=email, rol=role, primer_ingreso=False)
            owner = uuid4()
            connection.execute(text("""
                INSERT INTO propietarios (id, nombre_completo, dni, email, telefono)
                VALUES (:id, 'Titular Sintetico', :dni, :email, '+5490000000000')
            """), {"id": owner, "dni": str(10_000_000 + owner.int % 90_000_000),
                   "email": f"qa-hu15-owner-{marker}@example.com"})
            identities.append(("propietarios", owner))
            factory = sessionmaker(bind=connection, class_=RollbackSession, join_transaction_mode="create_savepoint")
            claims = SqlAlchemyClaimsRepository(factory)
            cities = []
            for index in (1, 2):
                property_id, tenant, claim = [uuid4() for _ in range(3)]
                city = f"Localidad Sintetica {marker} {index}"
                cities.append(city)
                connection.execute(text("""
                    INSERT INTO propiedades (id, direccion, provincia, localidad, barrio, tipo, propietario_id)
                    VALUES (:id, :address, 'Córdoba', :city, 'Centro', 'casa', :owner)
                """), {"id": property_id, "address": f"Unidad sintetica HU15 {marker} {index}",
                       "city": city, "owner": owner})
                connection.execute(text("""
                    INSERT INTO inquilinos (id, nombre_completo, dni, email, telefono, propiedad_id)
                    VALUES (:id, 'Inquilino Sintetico', :dni, :email, '+5490000000000', :property)
                """), {"id": tenant, "dni": str(10_000_000 + tenant.int % 90_000_000),
                       "email": f"qa-hu15-tenant-{marker}-{index}@example.com", "property": property_id})
                connection.execute(text("""
                    INSERT INTO reclamos (id, numero, descripcion, urgencia, inquilino_id,
                        propiedad_id, operador_asignado_id)
                    VALUES (:id, :number, :description, 'media', :tenant, :property, :operator)
                """), {"id": claim, "number": 900_000_000_000 + claim.int % 10**12,
                       "description": f"Reclamo sintetico HU15 {marker} {index}: reparación de prueba.",
                       "tenant": tenant, "property": property_id, "operator": users["operador"].id})
                identities.extend([("propiedades", property_id), ("inquilinos", tenant), ("reclamos", claim)])
                claim_ids.append(claim)
                claims.persist_classification(claim, AgentClassificationResult(
                    tipo_gasto="ordinario", confianza=0.95, fundamento="Clasificación sintética de QA.",
                    debe_escalar=False, motivo_escalado=None, estado_clasificacion="clasificado",
                    actor_responsable="inquilino", notificacion_responsable_requerida=True,
                ))
                # El fixture original conserva su etapa para las regresiones;
                # las pruebas automáticas adicionales usan Recibido sin autorización.
                connection.execute(text("UPDATE reclamos SET estado='Pendiente de asignación' WHERE id=:id"), {"id": claim})
            specialty = uuid4()
            connection.execute(text("INSERT INTO especialidades (id, nombre) VALUES (:id,:name)"),
                               {"id": specialty, "name": f"Especialidad Sintetica HU15 {marker}"})
            identities.append(("especialidades", specialty))
            case = SimpleNamespace(connection=connection, factory=factory, marker=marker,
                                   repo=SqlAlchemyProviderCandidatesRepository(factory), users=users,
                                   claims=claim_ids, cities=cities, specialty=specialty, identities=identities)
            yield case
        finally:
            transaction.rollback()
            for table, identifier in identities:
                assert connection.execute(text(f"SELECT count(*) FROM {table} WHERE id=:id"),
                                          {"id": identifier}).scalar_one() == 0
            for claim in claim_ids:
                for table in ("reclamo_busquedas_proveedores", "reclamo_responsables",
                              "reclamo_historial_estados", "notificaciones"):
                    assert connection.execute(text(f"SELECT count(*) FROM {table} WHERE reclamo_id=:id"),
                                              {"id": claim}).scalar_one() == 0
                if connection.execute(text("SELECT to_regclass('public.reclamo_tareas_proveedores') IS NOT NULL")).scalar_one():
                    assert connection.execute(text("SELECT count(*) FROM reclamo_tareas_proveedores WHERE reclamo_id=:id"),
                                              {"id": claim}).scalar_one() == 0


@pytest.fixture
def case(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("HU15 QA no puede consultar Gemini, SMTP ni Storage reales.")
    monkeypatch.setattr("app.agents.classification.nodes.get_gemini_classifier", forbidden)
    monkeypatch.setattr("app.agents.provider_candidates.get_specialty_resolver", forbidden)
    monkeypatch.setattr("app.services.claim_notifications.SmtpClaimEmailSender.send", forbidden)
    monkeypatch.setattr("app.services.claim_storage.SupabaseClaimPhotoStorage.download", forbidden)
    with synthetic_context() as value:
        yield value


def provider(case, *, city=None, province="Córdoba", area=None, active=True):
    identifier, coverage = uuid4(), uuid4()
    c = case.connection
    c.execute(text("""
        INSERT INTO proveedores (id, nombre_razon_social, telefono, activo, hora_inicio, hora_fin)
        VALUES (:id, 'Proveedor Sintetico HU15', :phone, :active, '08:00', '17:00')
    """), {"id": identifier, "phone": "+54" + str(identifier.int)[:12], "active": active})
    c.execute(text("INSERT INTO proveedor_especialidades VALUES (:provider,:specialty)"),
              {"provider": identifier, "specialty": case.specialty})
    c.execute(text("""
        INSERT INTO proveedor_coberturas (id, proveedor_id, provincia, localidad, cubre_toda_localidad)
        VALUES (:id,:provider,:province,:city,:all)
    """), {"id": coverage, "provider": identifier, "province": province,
           "city": city or case.cities[0], "all": area is None})
    case.identities.extend([("proveedores", identifier), ("proveedor_coberturas", coverage)])
    if area:
        c.execute(text("INSERT INTO proveedor_cobertura_barrios (cobertura_id,barrio) VALUES (:id,:area)"),
                  {"id": coverage, "area": area})
    return identifier


def command(case, *, index=0, specialty=True):
    return CandidateSearchRequest(request_id=uuid4(), expected_updated_at=case.repo.get(case.claims[index]).updated_at,
                                  especialidad_id=case.specialty if specialty else None)


def execute(case, request, *, index=0, role="operador"):
    return case.repo.search(case.claims[index], request, origin=role, user_id=case.users[role].id)


def snapshot(case, index=0):
    claim = case.claims[index]
    data = {}
    for table, field in (("reclamos", "id"), ("reclamo_responsables", "reclamo_id"),
                         ("reclamo_historial_estados", "reclamo_id"), ("notificaciones", "reclamo_id"),
                         ("reclamo_busquedas_proveedores", "reclamo_id")):
        data[table] = [dict(row) for row in case.connection.execute(text(
            f"SELECT * FROM {table} WHERE {field}=:id ORDER BY 1"), {"id": claim}).mappings()]
    return data


def test_reads_then_search_exact_coverage_paginated_without_reclassification(case):
    expected = {provider(case), provider(case, area="Centro")}
    provider(case, city=case.cities[1])
    provider(case, province="Santa Fe")
    provider(case, area="Centro Norte")
    provider(case, active=False)
    before = snapshot(case)
    assert case.repo.get(case.claims[0]).resultado == "especialidad_pendiente"
    assert case.repo.list(search=case.marker, page_size=1).total_pages == 2
    assert snapshot(case) == before
    result = execute(case, command(case))
    assert set(result.candidato_ids) == expected and result.aviso_operador == "no_aplica"
    view = case.repo.get(case.claims[0], page_size=1)
    second = case.repo.get(case.claims[0], page=2, page_size=1)
    assert view.total == 2 and view.total_pages == 2 and view.historial_total == 1
    assert {view.candidatos[0].id, second.candidatos[0].id} == expected
    assert view.candidatos[0].hora_inicio is not None
    after = snapshot(case)
    for key in ("tipo_gasto", "fundamento_clasificacion", "confianza_clasificacion", "estado"):
        assert after["reclamos"][0][key] == before["reclamos"][0][key]
    for table in ("reclamo_responsables", "reclamo_historial_estados", "notificaciones"):
        assert after[table] == before[table]


def test_no_candidates_idempotency_audit_and_alert_deduplication(case):
    first = command(case)
    result = execute(case, first)
    assert result.resultado == "sin_candidatos" and result.aviso_operador == "encolado"
    replay = execute(case, first)
    assert replay.repetida and replay.busqueda_id == result.busqueda_id
    execute(case, command(case))
    assert case.repo.get(case.claims[0]).historial_total == 2
    alerts = case.connection.execute(text("""
        SELECT destinatario_contacto, estado_envio FROM notificaciones
        WHERE reclamo_id=:id AND clave_idempotencia LIKE '%:candidatos:%'
    """), {"id": case.claims[0]}).all()
    assert alerts == [(str(case.users["operador"].email), "pendiente")]
    with pytest.raises(CandidateSearchConflictError):
        execute(case, first.model_copy(update={"especialidad_id": None}))


def test_missing_specialty_and_agent_origin_are_audited(case):
    result = case.repo.search(case.claims[0], command(case, specialty=False), origin="agente", user_id=None)
    assert result.resultado == "especialidad_pendiente" and result.aviso_operador == "encolado"
    audit = case.repo.get(case.claims[0]).historial_busquedas[0]
    assert audit.origen == "agente" and audit.usuario_id is None


@pytest.mark.parametrize("state", ["Resuelto", "Rechazado por propietario", "Sesión expirada"])
def test_closed_states_never_allow_another_search(case, state):
    case.connection.execute(text("UPDATE reclamos SET estado=:state WHERE id=:id"),
                            {"state": state, "id": case.claims[0]})
    before = snapshot(case)
    assert not case.repo.get(case.claims[0]).puede_buscar
    assert case.repo.list(search=case.marker).total == 1
    with pytest.raises(CandidateSearchConflictError):
        execute(case, command(case))
    assert snapshot(case) == before


def test_stale_version_unknown_specialty_and_inactive_user_are_safe(case):
    before = snapshot(case)
    with pytest.raises(CandidateSearchConflictError):
        execute(case, command(case).model_copy(update={
            "expected_updated_at": case.repo.get(case.claims[0]).updated_at - timedelta(seconds=1)}))
    with pytest.raises(CandidateSpecialtyNotFoundError):
        execute(case, command(case).model_copy(update={"especialidad_id": uuid4()}))
    case.connection.execute(text("UPDATE usuarios SET activo=false WHERE id=:id"),
                            {"id": case.users["operador"].id})
    with pytest.raises(CandidateSearchPermissionError):
        execute(case, command(case))
    assert snapshot(case) == before


def test_audit_failure_rolls_back_specialty_and_outbox(case):
    request = command(case)
    before = snapshot(case)
    def fail(conn, cursor, statement, parameters, context, many):
        if "INSERT INTO reclamo_busquedas_proveedores" in statement:
            raise RuntimeError("Fallo sintético de auditoría.")
    event.listen(case.connection, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            execute(case, request)
    finally:
        event.remove(case.connection, "before_cursor_execute", fail)
    assert snapshot(case) == before


@pytest.mark.parametrize("role", ["operador", "administrador"])
def test_real_http_validations_private_routes_and_safe_replay(case, role):
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_current_user] = lambda: case.users[role]
    test_app.dependency_overrides[get_candidates_repository] = lambda: case.repo
    with TestClient(test_app) as client:
        assert client.get("/reclamos/pendientes-asignacion", params={"search": case.marker}).json()["total"] == 2
        url = f"/reclamos/{case.claims[0]}/buscar-proveedores"
        request = command(case).model_dump(mode="json")
        response = client.post(url, json=request)
        assert response.status_code == 200 and response.json()["resultado"] == "sin_candidatos"
        assert client.post(url, json=request).json()["repetida"]
        assert client.get(f"/reclamos/{case.claims[0]}/proveedores-candidatos").json()["historial_total"] == 1
        # now() del trigger permanece fijo en la transacción externa de QA.
        # Una versión explícitamente anterior prueba el rechazo sin asumir
        # que los savepoints crean nuevas fechas de inicio de transacción.
        stale = command(case)
        stale = stale.model_copy(update={"expected_updated_at": stale.expected_updated_at - timedelta(seconds=1)})
        assert client.post(url, json=stale.model_dump(mode="json")).status_code == 409
        assert case.repo.get(case.claims[0]).historial_total == 1
        assert client.post(url, json={**command(case).model_dump(mode="json"), "origen": "agente"}).status_code == 422
        test_app.dependency_overrides[get_current_user] = lambda: case.users[role].model_copy(update={"rol": "inquilino"})
        assert client.get("/reclamos/pendientes-asignacion").status_code == 403
        test_app.dependency_overrides[get_current_user] = lambda: case.users[role].model_copy(update={"primer_ingreso": True})
        assert client.get("/reclamos/pendientes-asignacion").status_code == 403
