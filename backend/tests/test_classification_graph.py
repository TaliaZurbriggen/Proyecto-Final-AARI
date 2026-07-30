"""Pruebas del grafo de clasificaci?n con un proveedor simulado."""

import pytest

from app.agents.classification.graph import build_classification_graph
from app.agents.classification.llm import build_classification_prompt, get_gemini_classifier


class FakeClassifier:
    """Doble que permite verificar el grafo sin consumir la API de Gemini."""

    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.prompt: str | None = None
        self.response = response or {
            "tipo_gasto": "ordinario",
            "confianza": 0.92,
            "fundamento": "La reparaci?n de una canilla corresponde al mantenimiento habitual.",
            "debe_escalar": False,
            "motivo_escalado": None,
        }

    def invoke(self, prompt: str) -> dict[str, object]:
        self.prompt = prompt
        return self.response


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


def invoke_graph(classifier: object, confidence_threshold: float = 0.75) -> dict[str, object]:
    graph = build_classification_graph(classifier, confidence_threshold)
    return graph.invoke(
        {
            "descripcion": "La canilla de la cocina pierde agua al abrirla.",
            "urgencia": "media",
        }
    )


def test_graph_classifies_a_high_confidence_claim():
    classifier = FakeClassifier()

    result = invoke_graph(classifier)

    assert result["tipo_gasto"] == "ordinario"
    assert result["confianza"] == 0.92
    assert result["debe_escalar"] is False
    assert result["motivo_escalado"] is None
    assert result["estado_clasificacion"] == "clasificado"
    assert classifier.prompt is not None
    assert "La canilla de la cocina pierde agua al abrirla." in classifier.prompt
    assert '"plomeria-01"' in classifier.prompt
    assert "0.75" in classifier.prompt


def test_graph_escalates_a_low_confidence_claim():
    classifier = FakeClassifier(
        {
            "tipo_gasto": "extraordinario",
            "confianza": 0.74,
            "fundamento": "La causa no qued? completamente determinada.",
            "debe_escalar": False,
            "motivo_escalado": None,
        }
    )

    result = invoke_graph(classifier)

    assert result["tipo_gasto"] is None
    assert result["confianza"] == 0.74
    assert result["fundamento"] == "La causa no qued? completamente determinada."
    assert result["debe_escalar"] is True
    assert result["motivo_escalado"] == "confianza_insuficiente"
    assert result["estado_clasificacion"] == "escalado"


def test_graph_classifies_at_the_confidence_threshold():
    classifier = FakeClassifier(
        {
            "tipo_gasto": "expensa",
            "confianza": 0.75,
            "fundamento": "Es un gasto habitual de consorcio.",
            "debe_escalar": False,
            "motivo_escalado": None,
        }
    )

    result = invoke_graph(classifier)

    assert result["tipo_gasto"] == "expensa"
    assert result["estado_clasificacion"] == "clasificado"


def test_graph_preserves_a_valid_escalation_from_the_model():
    classifier = FakeClassifier(
        {
            "tipo_gasto": None,
            "confianza": 0.9,
            "fundamento": "El reclamo menciona olor a gas.",
            "debe_escalar": True,
            "motivo_escalado": "riesgo_seguridad",
        }
    )

    result = invoke_graph(classifier)

    assert result["tipo_gasto"] is None
    assert result["motivo_escalado"] == "riesgo_seguridad"
    assert result["estado_clasificacion"] == "escalado"


def test_prompt_uses_fallbacks_for_domain_data_not_available():
    prompt = build_classification_prompt(
        {
            "descripcion": "No enfr?a la heladera provista.",
            "urgencia": "baja",
        },
        confidence_threshold=0.75,
    )

    assert "Rubro declarado por el inquilino: no disponible" in prompt
    assert "contractuales de la propiedad: []" in prompt
    assert "{{BASE_CONOCIMIENTO_JSON}}" not in prompt
    assert "{{umbral_confianza}}" not in prompt


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
            "fundamento": "Categor?a fuera del contrato.",
            "debe_escalar": False,
            "motivo_escalado": None,
        },
        {
            "tipo_gasto": "expensa",
            "confianza": 1.2,
            "fundamento": "Confianza fuera de rango.",
            "debe_escalar": False,
            "motivo_escalado": None,
        },
        {
            "tipo_gasto": "extraordinario",
            "confianza": 0.7,
            "fundamento": "",
            "debe_escalar": False,
            "motivo_escalado": None,
        },
        {
            "tipo_gasto": "ordinario",
            "confianza": 0.8,
            "fundamento": "Salida contradictoria.",
            "debe_escalar": True,
            "motivo_escalado": "riesgo_seguridad",
        },
        None,
    ],
    ids=[
        "missing-required-field",
        "invalid-expense-type",
        "confidence-out-of-range",
        "empty-reason",
        "inconsistent-escalation-contract",
        "null-response",
    ],
)
def test_graph_escalates_an_invalid_model_response(response):
    result = invoke_graph(InvalidResponseClassifier(response))

    assert_invalid_response_is_escalated(result)


def test_graph_escalates_when_the_provider_raises_an_error():
    result = invoke_graph(FailingClassifier())

    assert_invalid_response_is_escalated(result)
    assert "detalle interno del proveedor" not in str(result)


def test_gemini_classifier_requires_a_local_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Falta GEMINI_API_KEY"):
        get_gemini_classifier()
