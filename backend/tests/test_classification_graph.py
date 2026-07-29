"""Pruebas del grafo de clasificación con un proveedor simulado."""

import pytest

from app.agents.classification.graph import build_classification_graph
from app.agents.classification.llm import get_gemini_classifier


class FakeClassifier:
    """Doble que permite verificar el grafo sin consumir la API de Gemini."""

    def __init__(self) -> None:
        self.prompt: str | None = None

    def invoke(self, prompt: str) -> dict[str, object]:
        self.prompt = prompt
        return {
            "tipo_gasto": "ordinario",
            "confianza": 0.92,
            "fundamento": "La reparación de una canilla corresponde al mantenimiento habitual.",
        }


class InvalidResponseClassifier:
    """Doble que devuelve una respuesta configurable sin llamar a Gemini."""

    def __init__(self, response: object) -> None:
        self.response = response

    def invoke(self, prompt: str) -> object:
        return self.response


class FailingClassifier:
    """Doble que simula un error del proveedor externo."""

    def invoke(self, prompt: str) -> dict[str, object]:
        raise RuntimeError("detalle interno del proveedor")


def assert_invalid_response_is_escalated(result: dict[str, object]) -> None:
    assert result["tipo_gasto"] is None
    assert result["confianza"] is None
    assert result["fundamento"] is None
    assert result["debe_escalar"] is True
    assert result["motivo_escalado"] == "respuesta_modelo_invalida"
    assert result["estado_clasificacion"] == "escalado"


def test_graph_processes_a_claim_with_an_injected_classifier():
    classifier = FakeClassifier()
    graph = build_classification_graph(classifier)

    result = graph.invoke(
        {
            "descripcion": "La canilla de la cocina pierde agua al abrirla.",
            "urgencia": "media",
        }
    )

    assert result["descripcion"] == "La canilla de la cocina pierde agua al abrirla."
    assert result["urgencia"] == "media"
    assert result["tipo_gasto"] == "ordinario"
    assert result["confianza"] == 0.92
    assert result["fundamento"] == "La reparación de una canilla corresponde al mantenimiento habitual."
    assert classifier.prompt is not None
    assert "La canilla de la cocina pierde agua al abrirla." in classifier.prompt


@pytest.mark.parametrize(
    "response",
    [
        {
            "tipo_gasto": "ordinario",
            "confianza": 0.8,
        },
        {
            "tipo_gasto": "desconocido",
            "confianza": 0.8,
            "fundamento": "Categoría fuera del contrato.",
        },
        {
            "tipo_gasto": "expensa",
            "confianza": 1.2,
            "fundamento": "Confianza fuera de rango.",
        },
        {
            "tipo_gasto": "extraordinario",
            "confianza": 0.7,
            "fundamento": "",
        },
        None,
    ],
    ids=[
        "missing-required-field",
        "invalid-expense-type",
        "confidence-out-of-range",
        "empty-reason",
        "null-response",
    ],
)
def test_graph_escalates_an_invalid_model_response(response):
    graph = build_classification_graph(InvalidResponseClassifier(response))

    result = graph.invoke(
        {
            "descripcion": "El modelo debe devolver una clasificación válida.",
            "urgencia": "media",
        }
    )

    assert_invalid_response_is_escalated(result)


def test_graph_escalates_when_the_provider_raises_an_error():
    graph = build_classification_graph(FailingClassifier())

    result = graph.invoke(
        {
            "descripcion": "El proveedor no puede completar la clasificación.",
            "urgencia": "alta",
        }
    )

    assert_invalid_response_is_escalated(result)
    assert "detalle interno del proveedor" not in str(result)


def test_gemini_classifier_requires_a_local_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Falta GEMINI_API_KEY"):
        get_gemini_classifier()