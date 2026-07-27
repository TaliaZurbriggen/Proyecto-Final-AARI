"""Pruebas del grafo base de clasificación."""

from app.agents.classification.graph import build_classification_graph


def test_graph_processes_a_claim_without_calling_a_model():
    graph = build_classification_graph()

    result = graph.invoke(
        {
            "descripcion": "La canilla de la cocina pierde agua al abrirla.",
            "urgencia": "media",
        }
    )

    assert result["descripcion"] == "La canilla de la cocina pierde agua al abrirla."
    assert result["urgencia"] == "media"
    assert result["estado_clasificacion"] == "pendiente_modelo"