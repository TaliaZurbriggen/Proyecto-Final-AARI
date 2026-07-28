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


def test_gemini_classifier_requires_a_local_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Falta GEMINI_API_KEY"):
        get_gemini_classifier()