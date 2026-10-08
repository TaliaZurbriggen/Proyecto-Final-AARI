"""Recorrido HU31 → HU13 con HTTP y PostgreSQL real, sin servicios externos."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents.classification.graph import build_manual_classification_graph
from app.api.admin_home import get_admin_home_repository
from app.api.auth import get_current_user, require_admin
from app.api.escalados import get_escalated_repository, get_manual_service
from app.api.reclamos import get_claim_notification_service
from app.db.admin_home import SqlAlchemyAdminHomeRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.services.escalated_claims_service import EscalatedClaimsService
from tests.test_escalados_postgres import escalated_case, hu13_case
from tests.test_responsible_actor_postgres import claim_case, local_engine, snapshot


pytestmark = pytest.mark.skipif(
    not os.getenv("AARI_TEST_POSTGRES_URL"), reason="Requiere PostgreSQL local dedicado.",
)


@pytest.mark.parametrize("role", ["administrador", "operador"])
@pytest.mark.parametrize("expense", ["ordinario", "extraordinario", "expensa"])
def test_home_pending_matches_queue_before_and_after_manual_decision(escalated_case, role, expense):
    db, repo, queue, claim_id, operator = escalated_case
    with db.begin() as connection:
        admin_id = connection.execute(text("""
            INSERT INTO usuarios (email, password_hash, rol, primer_ingreso)
            VALUES ('admin@example.com', 'not-a-credential', 'administrador', false) RETURNING id
        """)).scalar_one()
        connection.execute(text("""
            UPDATE reclamos SET contexto_contractual_clasificacion='[{"texto":"Cláusula sintética"}]'::jsonb
            WHERE id=:id
        """), {"id": claim_id})
    admin = AuthenticatedUser(id=admin_id, email="admin@example.com", rol="administrador", primer_ingreso=False)
    staff = admin if role == "administrador" else AuthenticatedUser(
        id=operator.user_id, email="operator@example.com", rol="operador", primer_ingreso=False,
    )
    current = {"user": admin}
    delivery_attempts = []

    class LocalDeliveryDouble:
        def deliver(self, notification_id):
            # Capturar el background task sin SMTP ni modificar la entrega real.
            delivery_attempts.append(notification_id)
            return False

    previous = app.dependency_overrides.copy()
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.update({
        get_current_user: lambda: current["user"],
        get_admin_home_repository: lambda: SqlAlchemyAdminHomeRepository(repo.session_factory),
        get_escalated_repository: lambda: queue,
        get_manual_service: lambda: EscalatedClaimsService(repo, build_manual_classification_graph()),
        get_claim_notification_service: LocalDeliveryDouble,
    })
    try:
        with TestClient(app) as client:
            summary = client.get("/admin/resumen")
            listed = client.get("/reclamos/escalados?page_size=1")
            assert summary.status_code == listed.status_code == 200
            assert summary.json()["reclamos"] == {"activos": 1, "pendientes_clasificacion": listed.json()["total"]}
            assert listed.json()["total"] == 1
            detail = client.get(f"/reclamos/escalados/{claim_id}")
            assert detail.status_code == 200 and detail.json()["puede_resolver"]
            current["user"] = staff
            body = {"tipo_gasto": expense, "fundamento": "La revisión manual confirmó la causa del desperfecto.",
                    "expected_updated_at": detail.json()["updated_at"]}
            saved = client.post(f"/reclamos/{claim_id}/resolver-escalado", json=body)
            assert saved.status_code == 200
            assert saved.json()["tipo_gasto"] == expense
            assert client.post(f"/reclamos/{claim_id}/resolver-escalado", json=body).status_code == 409
            current["user"] = admin
            updated = client.get("/admin/resumen")
            empty_queue = client.get("/reclamos/escalados")
            assert updated.status_code == empty_queue.status_code == 200
            assert updated.json()["reclamos"] == {"activos": 1, "pendientes_clasificacion": 0}
            assert empty_queue.json()["total"] == 0 and empty_queue.json()["items"] == []
            assert client.get(f"/reclamos/escalados/{claim_id}").json()["puede_resolver"] is False
        data = snapshot(db, claim_id)
        assert data["reclamos"][0]["estado"] == "Pendiente de respuesta del responsable"
        assert data["reclamos"][0]["contexto_contractual_clasificacion"] == [{"texto": "Cláusula sintética"}]
        assert queue.get(claim_id).decisiones[0].rol == role
        expected_event = "expensa_reporte" if expense == "expensa" else "responsable_inicial"
        events = [entry for entry in data["notificaciones"] if entry["tipo_evento"] == expected_event]
        assert len(events) == len(delivery_attempts) == 1
        assert len(data["reclamo_responsables"]) == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
