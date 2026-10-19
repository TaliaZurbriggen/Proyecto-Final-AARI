"""HU17: transición determinista; el modelo no elige por la persona."""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class ProviderChoiceState(TypedDict, total=False):
    tipo_proveedor: Literal["fidelizado", "propio"]
    siguiente_paso: str
    estado_resultante: str


def build_provider_choice_graph():
    def route(state):
        if state["tipo_proveedor"] not in {"fidelizado", "propio"}:
            raise ValueError("Tipo de proveedor inválido.")
        return state["tipo_proveedor"]

    graph = StateGraph(ProviderChoiceState)
    graph.add_node("decision", lambda state: {})
    graph.add_node("fidelizado", lambda state: {
        "siguiente_paso": "solicitar_presupuestos", "estado_resultante": "Pendiente de asignación"})
    graph.add_node("propio", lambda state: {
        "siguiente_paso": "registrar_proveedor_propio", "estado_resultante": "Pendiente de datos de proveedor propio"})
    graph.add_edge(START, "decision")
    graph.add_conditional_edges("decision", route, {"fidelizado": "fidelizado", "propio": "propio"})
    graph.add_edge("fidelizado", END)
    graph.add_edge("propio", END)
    return graph.compile()


provider_choice_graph = build_provider_choice_graph()
