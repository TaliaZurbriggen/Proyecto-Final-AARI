"""HU13 real: datos exclusivamente sintéticos, rollback y ningún envío externo.

No reutiliza ni modifica reclamos/personas existentes. El número sintético
se pasa explícitamente para no consumir la secuencia real del negocio.
"""

from datetime import timedelta
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.agents.classification.graph import build_manual_classification_graph
from app.api.auth import get_current_user
from app.api.escalados import get_escalated_repository, get_manual_service
from app.api.reclamos import get_claim_notification_service
from app.db.database import engine
from app.db.escalados import SqlAlchemyEscalatedClaimsRepository
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.escalados import ManualClassificationRequest
from app.schemas.reclamos import AgentClassificationResult
from app.services.escalated_claims_service import (
    EscalatedClaimsService, ManualClassificationConflictError,
    ManualClassificationPermissionError, ManualDecisionContext,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_HU13_SUPABASE_INTEGRATION") != "1",
    reason="Requiere autorización explícita para HU13 en Supabase con rollback.",
)


@pytest.fixture
def synthetic_case(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("El QA HU13 no puede consultar Gemini, SMTP ni Storage reales.")
    monkeypatch.setattr("app.agents.classification.nodes.get_gemini_classifier", forbidden)
    monkeypatch.setattr("app.services.claim_notifications.SmtpClaimEmailSender.send", forbidden)
    monkeypatch.setattr("app.services.claim_storage.SupabaseClaimPhotoStorage.download", forbidden)
    owner_id, property_id, tenant_id, operator_id, admin_id, claim_id = [uuid4() for _ in range(6)]
    marker = uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            for user_id, role, name in [(operator_id, "operador", "Operador Sintetico"),
                                        (admin_id, "administrador", None)]:
                connection.execute(text("""
                    INSERT INTO usuarios (id, email, password_hash, rol, primer_ingreso, nombre_completo)
                    VALUES (:id, :email, 'not-a-credential', CAST(:role AS rol_usuario), false, :name)
                """), {"id": user_id, "email": f"qa-hu13-{role}-{marker}@example.com", "role": role, "name": name})
            connection.execute(text("""
                INSERT INTO propietarios (id, nombre_completo, dni, email, telefono)
                VALUES (:id, 'Titular Sintetico', :dni, :email, '+5490000000000')
            """), {"id": owner_id, "dni": str(10_000_000 + owner_id.int % 90_000_000),
                    "email": f"qa-hu13-owner-{marker}@example.com"})
            connection.execute(text("""
                INSERT INTO propiedades (id, direccion, provincia, localidad, tipo, propietario_id)
                VALUES (:id, :address, 'Córdoba', 'Localidad de prueba', 'casa', :owner)
            """), {"id": property_id, "address": f"Unidad sintetica HU13 {marker}", "owner": owner_id})
            connection.execute(text("""
                INSERT INTO inquilinos (id, nombre_completo, dni, email, telefono, propiedad_id)
                VALUES (:id, 'Inquilino Sintetico', :dni, :email, '+5490000000000', :property)
            """), {"id": tenant_id, "dni": str(10_000_000 + tenant_id.int % 90_000_000),
                    "email": f"qa-hu13-tenant-{marker}@example.com", "property": property_id})
            connection.execute(text("""
                INSERT INTO reclamos (id, numero, descripcion, urgencia, inquilino_id,
                    propiedad_id, operador_asignado_id)
                VALUES (:id, :number, :description, 'media', :tenant, :property, :operator)
            """), {"id": claim_id, "number": 900_000_000_000 + claim_id.int % 10**12,
                    "description": f"Reclamo sintetico HU13 {marker}: causa no confirmada.",
                    "tenant": tenant_id, "property": property_id, "operator": operator_id})
            factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
            repository = SqlAlchemyClaimsRepository(factory)
            queries = SqlAlchemyEscalatedClaimsRepository(factory)
            repository.persist_classification(claim_id, AgentClassificationResult(
                tipo_gasto=None, confianza=0.55, fundamento="El origen no está confirmado.",
                debe_escalar=True, motivo_escalado="confianza_insuficiente",
                estado_clasificacion="escalado", actor_responsable=None,
                notificacion_responsable_requerida=False,
            ))
            users = {
                role: AuthenticatedUser(id=user_id, email=f"qa-hu13-{role}-{marker}@example.com",
                                        rol=role, primer_ingreso=False)
                for role, user_id in [("operador", operator_id), ("administrador", admin_id)]
            }
            yield connection, repository, queries, claim_id, users, marker
        finally:
            transaction.rollback()
            # Verificar por IDs propios, no por conteos globales que otro desarrollador puede cambiar.
            for table, row_id in [("reclamos", claim_id), ("propietarios", owner_id),
                                  ("propiedades", property_id), ("inquilinos", tenant_id),
                                  ("usuarios", operator_id), ("usuarios", admin_id)]:
                assert connection.execute(text(f"SELECT count(*) FROM {table} WHERE id = :id"),
                                          {"id": row_id}).scalar_one() == 0
            for table in ("reclamo_decisiones_clasificacion", "reclamo_responsables",
                          "reclamo_historial_estados", "notificaciones"):
                assert connection.execute(text(f"SELECT count(*) FROM {table} WHERE reclamo_id = :id"),
                                          {"id": claim_id}).scalar_one() == 0


@pytest.mark.parametrize("role", ["operador", "administrador"])
@pytest.mark.parametrize("expense,actor", [("ordinario", "inquilino"),
    ("extraordinario", "propietario"), ("expensa", "inmobiliaria")])
def test_real_manual_graph_audit_actor_outbox_and_rollback(synthetic_case, role, expense, actor):
    connection, repository, queries, claim_id, users, marker = synthetic_case
    assert any(item.id == claim_id for item in queries.list(search=marker).items)
    before = queries.get(claim_id)
    service = EscalatedClaimsService(repository, build_manual_classification_graph())
    request = ManualClassificationRequest(tipo_gasto=expense,
        fundamento="La revisión sintética confirma el tipo de gasto.", expected_updated_at=before.updated_at)
    result = service.resolve(claim_id, request, users[role])
    assert result.response.actor_responsable == actor and result.response.origen == role
    assert result.notification_id is not None
    after = queries.get(claim_id)
    assert not after.puede_resolver and after.confianza_clasificacion is None
    assert len(after.decisiones) == 1
    decision = after.decisiones[0]
    assert decision.usuario_id == users[role].id and decision.rol == role
    assert decision.resultado_anterior["confianza"] == 0.55
    assert decision.resultado_anterior["motivo_escalado"] == "confianza_insuficiente"
    assert decision.fundamento == request.fundamento
    # PostgreSQL now() es estable en la transacción externa de rollback.
    # Las transiciones pueden compartir timestamp; un UUID no indica cronología.
    manual_history = [item for item in after.historial
                      if item.estado_nuevo == "Pendiente de respuesta del responsable"]
    assert len(manual_history) == 1 and manual_history[0].origen == role
    assert connection.execute(text("""
        SELECT usuario_id FROM reclamo_historial_estados
        WHERE reclamo_id = :id AND estado_nuevo = 'Pendiente de respuesta del responsable'
    """), {"id": claim_id}).scalar_one() == users[role].id
    assert queries.list(search=marker).total == 0
    assert connection.execute(text("""
        SELECT actor_tipo FROM reclamo_responsables WHERE reclamo_id = :id
    """), {"id": claim_id}).scalar_one() == actor
    assert connection.execute(text("""
        SELECT count(*) FROM notificaciones WHERE reclamo_id = :id AND tipo_evento = 'responsable_inicial'
    """), {"id": claim_id}).scalar_one() == 1
    with pytest.raises(ManualClassificationConflictError):
        service.resolve(claim_id, request, users[role])
    assert queries.get(claim_id).model_dump() == after.model_dump()


def test_real_stale_version_and_inactive_user_have_no_side_effects(synthetic_case):
    connection, repository, queries, claim_id, users, _ = synthetic_case
    before = queries.get(claim_id)
    user = users["operador"]
    result = AgentClassificationResult(
        tipo_gasto="ordinario", confianza=None, fundamento="Clasificación manual sintética.",
        debe_escalar=False, motivo_escalado=None, estado_clasificacion="clasificado",
        actor_responsable="inquilino", notificacion_responsable_requerida=True,
    )
    with pytest.raises(ManualClassificationConflictError):
        repository.resolve_manual(claim_id, result, ManualDecisionContext(
            user.id, user.rol, before.updated_at - timedelta(seconds=1)))
    connection.execute(text("UPDATE usuarios SET activo = false WHERE id = :id"), {"id": user.id})
    with pytest.raises(ManualClassificationPermissionError):
        repository.resolve_manual(claim_id, result, ManualDecisionContext(user.id, user.rol, before.updated_at))
    assert queries.get(claim_id).model_dump() == before.model_dump()


def test_real_queue_entry_is_private_and_not_duplicated_within_the_queue(synthetic_case):
    connection, _, queries, claim_id, users, _ = synthetic_case
    assert connection.execute(text("""
        SELECT destinatario_contacto FROM notificaciones
        WHERE reclamo_id = :id AND tipo_evento = 'alerta_operador'
    """), {"id": claim_id}).scalar_one() == str(users["operador"].email)
    connection.execute(text("UPDATE reclamos SET estado = 'Clasificación pendiente' WHERE id = :id"), {"id": claim_id})
    assert queries.get(claim_id).puede_resolver
    assert connection.execute(text("""
        SELECT count(*) FROM notificaciones WHERE reclamo_id = :id AND tipo_evento = 'alerta_operador'
    """), {"id": claim_id}).scalar_one() == 1
    for role in ("anon", "authenticated"):
        assert not connection.execute(text("""
            SELECT has_table_privilege(:role, 'public.reclamo_decisiones_clasificacion', 'SELECT,INSERT,UPDATE,DELETE')
        """), {"role": role}).scalar_one()


def test_real_http_flow_uses_local_graph_and_mock_delivery(synthetic_case):
    _, repository, queries, claim_id, users, _ = synthetic_case
    sent = []
    class Notifications:
        def deliver(self, notification_id):
            sent.append(notification_id)
    app.dependency_overrides[get_current_user] = lambda: users["operador"]
    app.dependency_overrides[get_escalated_repository] = lambda: queries
    app.dependency_overrides[get_manual_service] = lambda: EscalatedClaimsService(repository, build_manual_classification_graph())
    app.dependency_overrides[get_claim_notification_service] = Notifications
    try:
        with TestClient(app) as client:
            detail = client.get(f"/reclamos/escalados/{claim_id}")
            assert detail.status_code == 200
            response = client.post(f"/reclamos/{claim_id}/resolver-escalado", json={
                "tipo_gasto": "ordinario", "fundamento": "La revisión sintética confirmó mantenimiento habitual.",
                "expected_updated_at": detail.json()["updated_at"],
            })
            assert response.status_code == 200
            assert response.json()["estado"] == "Pendiente de respuesta del responsable"
            assert len(sent) == 1
            assert client.post(f"/reclamos/{claim_id}/resolver-escalado", json={
                "tipo_gasto": "expensa", "fundamento": "No debe sobreescribirse esta clasificación.",
                "expected_updated_at": detail.json()["updated_at"],
            }).status_code == 409
            assert len(sent) == 1 and len(queries.get(claim_id).decisiones) == 1
    finally:
        for dependency in (get_current_user, get_escalated_repository, get_manual_service, get_claim_notification_service):
            app.dependency_overrides.pop(dependency, None)
