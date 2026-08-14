"""Pruebas de integración del flujo HTTP usando el grafo real sin APIs externas."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.agents.classification.graph import build_classification_graph
from app.api.reclamos import get_classification_service
from app.main import app
from app.schemas.reclamos import AgentClassificationResult, ClaimClassificationResponse
from app.services.classification_service import ClaimForClassification, ClassificationService


class ControlledClassifier:
    """Proveedor controlado que permite recorrer LangGraph sin consumir Gemini."""

    def __init__(self, response: object) -> None:
        self.response = response
        self.prompt: str | None = None

    def invoke(self, prompt: str) -> object:
        self.prompt = prompt
        return self.response


@dataclass
class InMemoryClaimsRepository:
    """Repositorio en memoria que conserva el resultado recibido del servicio."""

    claim: ClaimForClassification
    persisted: AgentClassificationResult | None = None

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        return self.claim if self.claim.reclamo_id == reclamo_id else None

    def persist_classification(
        self,
        reclamo_id: UUID,
        result: AgentClassificationResult,
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


def classify_through_http(
    model_response: object,
    *,
    descripcion: str,
    urgencia: str = "media",
    rubro_declarado: str | None = "plomeria",
    clausulas_contrato: list[dict[str, object]] | None = None,
) -> tuple[
    ClaimClassificationResponse,
    InMemoryClaimsRepository,
    ControlledClassifier,
]:
    """Ejecuta endpoint -> servicio -> LangGraph -> persistencia en memoria."""

    reclamo_id = uuid4()
    repository = InMemoryClaimsRepository(
        ClaimForClassification(
            reclamo_id=reclamo_id,
            descripcion=descripcion,
            urgencia=urgencia,
            rubro_declarado=rubro_declarado,
            clausulas_contrato=clausulas_contrato or [],
        )
    )
    classifier = ControlledClassifier(model_response)
    graph = build_classification_graph(classifier, confidence_threshold=0.75)
    service = ClassificationService(repository, graph)
    app.dependency_overrides[get_classification_service] = lambda: service

    try:
        with TestClient(app) as client:
            http_response = client.post(f"/reclamos/{reclamo_id}/clasificar")
    finally:
        app.dependency_overrides.clear()

    assert http_response.status_code == 200
    return (
        ClaimClassificationResponse.model_validate(http_response.json()),
        repository,
        classifier,
    )


def test_complete_flow_classifies_and_persists_a_high_confidence_claim():
    descripcion = "La canilla de la cocina gotea por desgaste de la goma."

    response, repository, classifier = classify_through_http(
        {
            "tipo_gasto": "ordinario",
            "confianza": 0.92,
            "fundamento": "Es mantenimiento habitual de la grifería.",
            "debe_escalar": False,
            "motivo_escalado": None,
        },
        descripcion=descripcion,
    )

    assert response.estado == "Clasificado"
    assert response.tipo_gasto == "ordinario"
    assert response.debe_escalar is False
    assert repository.persisted is not None
    assert repository.persisted.estado_clasificacion == "clasificado"
    assert classifier.prompt is not None
    assert descripcion in classifier.prompt
    assert '"plomeria-01"' in classifier.prompt


def test_complete_flow_forces_escalation_below_the_confidence_threshold():
    response, repository, _ = classify_through_http(
        {
            "tipo_gasto": "extraordinario",
            "confianza": 0.74,
            "fundamento": "La causa probable no quedó completamente determinada.",
            "debe_escalar": False,
            "motivo_escalado": None,
        },
        descripcion="El termotanque dejó de funcionar y no sabemos por qué.",
    )

    assert response.estado == "Escalado"
    assert response.tipo_gasto is None
    assert response.confianza == 0.74
    assert response.motivo_escalado == "confianza_insuficiente"
    assert repository.persisted is not None
    assert repository.persisted.estado_clasificacion == "escalado"


def test_complete_flow_preserves_a_security_escalation_from_the_model():
    response, repository, _ = classify_through_http(
        {
            "tipo_gasto": None,
            "confianza": 0.96,
            "fundamento": "El olor a gas requiere intervención humana urgente.",
            "debe_escalar": True,
            "motivo_escalado": "riesgo_seguridad",
        },
        descripcion="Siento un fuerte olor a gas cerca de la cocina.",
        urgencia="alta",
        rubro_declarado="gas",
    )

    assert response.estado == "Escalado"
    assert response.tipo_gasto is None
    assert response.motivo_escalado == "riesgo_seguridad"
    assert repository.persisted is not None
    assert repository.persisted.motivo_escalado == "riesgo_seguridad"


def test_complete_flow_persists_the_safe_fallback_for_an_invalid_response():
    response, repository, _ = classify_through_http(
        {"tipo_gasto": "ordinario", "confianza": 0.9},
        descripcion="La descripción no permite identificar el inconveniente.",
        rubro_declarado=None,
    )

    assert response.estado == "Escalado"
    assert response.tipo_gasto is None
    assert response.confianza is None
    assert response.fundamento is None
    assert response.motivo_escalado == "respuesta_modelo_invalida"
    assert repository.persisted is not None
    assert repository.persisted.motivo_escalado == "respuesta_modelo_invalida"
