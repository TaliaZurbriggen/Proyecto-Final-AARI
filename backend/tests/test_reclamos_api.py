"""Pruebas del endpoint de clasificación sin Supabase ni Gemini."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from app.api.reclamos import get_claim_notification_service, get_classification_service
from app.main import app
from app.schemas.reclamos import AgentClassificationResult, ClaimClassificationResponse
from app.services.classification_service import (
    ClaimClassificationConflictError,
    ClaimForClassification,
    ClassificationService,
    PersistedClassification,
)


@dataclass
class FakeRepository:
    claim: ClaimForClassification | None
    persisted: AgentClassificationResult | None = None
    notification_id: UUID | None = None

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        return self.claim if self.claim and self.claim.reclamo_id == reclamo_id else None

    def persist_classification(
        self, reclamo_id: UUID, result: AgentClassificationResult,
        contract_context: list[dict[str, object]],
    ) -> PersistedClassification:
        self.persisted = result
        return PersistedClassification(
            response=ClaimClassificationResponse(
                reclamo_id=reclamo_id,
                estado=(
                    "Escalado"
                    if result.debe_escalar
                    else "Pendiente de respuesta del responsable"
                ),
                tipo_gasto=result.tipo_gasto,
                confianza=result.confianza,
                fundamento=result.fundamento,
                debe_escalar=result.debe_escalar,
                motivo_escalado=result.motivo_escalado,
            ),
            notification_id=self.notification_id,
        )


class FakeGraph:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.state: dict[str, object] | None = None

    def invoke(self, state: dict[str, object]) -> dict[str, object]:
        self.state = state
        return self.response


class FakeNotificationService:
    def __init__(self) -> None:
        self.delivered: list[UUID] = []

    def deliver(self, notification_id: UUID) -> bool:
        self.delivered.append(notification_id)
        return True


def build_client(
    repository: FakeRepository,
    graph: FakeGraph,
    notification_service: FakeNotificationService | None = None,
) -> TestClient:
    app.dependency_overrides[get_classification_service] = lambda: ClassificationService(
        repository, graph
    )
    if notification_service is not None:
        app.dependency_overrides[get_claim_notification_service] = (
            lambda: notification_service
        )
    return TestClient(app)


def test_endpoint_classifies_and_persists_an_existing_claim():
    reclamo_id = uuid4()
    repository = FakeRepository(
        ClaimForClassification(
            reclamo_id=reclamo_id,
            descripcion="La canilla de la cocina pierde agua al abrirla.",
            urgencia="media",
            rubro_declarado="plomería",
            clausulas_contrato=[],
        )
    )
    graph = FakeGraph(
        {
            "tipo_gasto": "ordinario",
            "confianza": 0.92,
            "fundamento": "Corresponde al mantenimiento habitual.",
            "debe_escalar": False,
            "motivo_escalado": None,
            "estado_clasificacion": "clasificado",
            "actor_responsable": "inquilino",
            "notificacion_responsable_requerida": True,
        }
    )

    with build_client(repository, graph) as client:
        response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "reclamo_id": str(reclamo_id),
        "estado": "Pendiente de respuesta del responsable",
        "tipo_gasto": "ordinario",
        "confianza": 0.92,
        "fundamento": "Corresponde al mantenimiento habitual.",
        "debe_escalar": False,
        "motivo_escalado": None,
        "origen": "agente",
    }
    assert repository.persisted is not None
    assert graph.state is not None
    assert graph.state["rubro_declarado"] == "plomería"


def test_endpoint_persists_an_escalated_claim():
    reclamo_id = uuid4()
    repository = FakeRepository(
        ClaimForClassification(
            reclamo_id=reclamo_id,
            descripcion="Se siente olor a gas en la cocina desde esta mañana.",
            urgencia="alta",
            rubro_declarado="gasista",
            clausulas_contrato=[],
        )
    )
    graph = FakeGraph(
        {
            "tipo_gasto": None,
            "confianza": 0.9,
            "fundamento": "Hay un posible riesgo de seguridad.",
            "debe_escalar": True,
            "motivo_escalado": "riesgo_seguridad",
            "estado_clasificacion": "escalado",
            "actor_responsable": None,
            "notificacion_responsable_requerida": False,
        }
    )

    with build_client(repository, graph) as client:
        response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["estado"] == "Escalado"
    assert response.json()["motivo_escalado"] == "riesgo_seguridad"
    assert repository.persisted is not None


def test_endpoint_returns_404_when_the_claim_does_not_exist():
    repository = FakeRepository(None)
    graph = FakeGraph({})

    with build_client(repository, graph) as client:
        response = client.post(f"/reclamos/{uuid4()}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Reclamo no encontrado."}


def test_endpoint_persists_the_safe_fallback_for_an_invalid_model_response():
    reclamo_id = uuid4()
    repository = FakeRepository(
        ClaimForClassification(
            reclamo_id=reclamo_id,
            descripcion="La descripción no permite identificar con claridad el problema.",
            urgencia="media",
            rubro_declarado=None,
            clausulas_contrato=[],
        )
    )
    graph = FakeGraph(
        {
            "tipo_gasto": None,
            "confianza": None,
            "fundamento": None,
            "debe_escalar": True,
            "motivo_escalado": "respuesta_modelo_invalida",
            "estado_clasificacion": "escalado",
            "actor_responsable": None,
            "notificacion_responsable_requerida": False,
        }
    )

    with build_client(repository, graph) as client:
        response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["estado"] == "Escalado"
    assert response.json()["tipo_gasto"] is None
    assert response.json()["confianza"] is None
    assert response.json()["fundamento"] is None
    assert response.json()["motivo_escalado"] == "respuesta_modelo_invalida"


def test_endpoint_attempts_the_responsible_notification_after_persisting():
    reclamo_id = uuid4()
    notification_id = uuid4()
    repository = FakeRepository(
        ClaimForClassification(
            reclamo_id=reclamo_id,
            descripcion="La canilla de la cocina pierde agua desde ayer.",
            urgencia="media",
            rubro_declarado="plomería",
            clausulas_contrato=[],
        ),
        notification_id=notification_id,
    )
    graph = FakeGraph(
        {
            "tipo_gasto": "ordinario",
            "confianza": 0.92,
            "fundamento": "Corresponde al mantenimiento habitual.",
            "debe_escalar": False,
            "motivo_escalado": None,
            "estado_clasificacion": "clasificado",
            "actor_responsable": "inquilino",
            "notificacion_responsable_requerida": True,
        }
    )
    notification_service = FakeNotificationService()

    with build_client(repository, graph, notification_service) as client:
        response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert notification_service.delivered == [notification_id]


@pytest.mark.parametrize(
    ("estado", "clasificado"),
    [
        ("Pendiente de respuesta del responsable", True),
        ("Pendiente de respuesta - vencido", True),
        ("Autorizado", False),
        ("Resuelto", False),
        ("Escalado", True),
        ("Recibido", True),
    ],
)
def test_reclassification_returns_409_before_calling_the_model(estado, clasificado):
    claim = ClaimForClassification(
        reclamo_id=uuid4(),
        descripcion="Descripción sintética de un reclamo de prueba.",
        urgencia="media",
        rubro_declarado=None,
        clausulas_contrato=[],
        estado=estado,
        clasificado=clasificado,
    )
    repository = FakeRepository(claim)
    graph = FakeGraph({})
    notifications = FakeNotificationService()
    try:
        with build_client(repository, graph, notifications) as client:
            response = client.post(f"/reclamos/{claim.reclamo_id}/clasificar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "No se puede volver a clasificar" in response.json()["detail"]
    assert graph.state is None
    assert repository.persisted is None
    assert notifications.delivered == []


def test_classification_race_returns_409_without_delivering_notifications():
    class ConcurrentRepository(FakeRepository):
        def persist_classification(self, reclamo_id, result, contract_context):
            raise ClaimClassificationConflictError("El reclamo avanzó de etapa.")

    claim = ClaimForClassification(
        reclamo_id=uuid4(),
        descripcion="Descripción sintética de un reclamo de prueba.",
        urgencia="media",
        rubro_declarado=None,
        clausulas_contrato=[],
    )
    graph = FakeGraph({
        "tipo_gasto": "ordinario", "confianza": 0.95,
        "fundamento": "Mantenimiento habitual.", "debe_escalar": False,
        "motivo_escalado": None, "estado_clasificacion": "clasificado",
        "actor_responsable": "inquilino", "notificacion_responsable_requerida": True,
    })
    notifications = FakeNotificationService()
    try:
        with build_client(ConcurrentRepository(claim), graph, notifications) as client:
            response = client.post(f"/reclamos/{claim.reclamo_id}/clasificar")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert graph.state is not None
    assert notifications.delivered == []
