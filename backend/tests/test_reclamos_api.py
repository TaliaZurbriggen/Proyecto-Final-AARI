"""Pruebas del endpoint de clasificación sin Supabase ni Gemini."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.reclamos import get_classification_service
from app.main import app
from app.schemas.reclamos import AgentClassificationResult, ClaimClassificationResponse
from app.services.classification_service import (
    ClaimForClassification,
    ClassificationService,
)


@dataclass
class FakeRepository:
    claim: ClaimForClassification | None
    persisted: AgentClassificationResult | None = None

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        return self.claim if self.claim and self.claim.reclamo_id == reclamo_id else None

    def persist_classification(
        self, reclamo_id: UUID, result: AgentClassificationResult
    ) -> ClaimClassificationResponse:
        self.persisted = result
        return ClaimClassificationResponse(
            reclamo_id=reclamo_id,
            estado="Escalado" if result.debe_escalar else "Clasificado",
            tipo_gasto=result.tipo_gasto,
            confianza=result.confianza,
            fundamento=result.fundamento,
            debe_escalar=result.debe_escalar,
            motivo_escalado=result.motivo_escalado,
        )


class FakeGraph:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.state: dict[str, object] | None = None

    def invoke(self, state: dict[str, object]) -> dict[str, object]:
        self.state = state
        return self.response


def build_client(repository: FakeRepository, graph: FakeGraph) -> TestClient:
    app.dependency_overrides[get_classification_service] = lambda: ClassificationService(
        repository, graph
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
        }
    )

    with build_client(repository, graph) as client:
        response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "reclamo_id": str(reclamo_id),
        "estado": "Clasificado",
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
