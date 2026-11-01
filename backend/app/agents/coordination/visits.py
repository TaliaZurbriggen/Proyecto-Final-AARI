"""Subgrafo HU23: reglas de avance, sin LLM y sin efectos externos."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class VisitState(TypedDict):
    etapa: str
    accion: str


TRANSITIONS = {
    ('esperando_disponibilidad', 'disponibilidad'): 'esperando_confirmacion',
    ('esperando_confirmacion', 'sin-coincidencia'): 'negociando',
    ('esperando_confirmacion', 'confirmar'): 'confirmada',
    ('negociando', 'proponer'): 'negociando',
    ('negociando', 'confirmar'): 'confirmada',
    ('esperando_confirmacion', 'vencer'): 'sin_acuerdo',
    ('negociando', 'vencer'): 'sin_acuerdo',
}


def _advance(state: VisitState):
    target = TRANSITIONS.get((state['etapa'], state['accion']))
    if target is None:
        raise ValueError('Esta acción no corresponde a la etapa actual.')
    return {'etapa': target}


def build_visit_graph():
    graph = StateGraph(VisitState)
    graph.add_node('coordinar_visita', _advance)
    graph.add_edge(START, 'coordinar_visita')
    graph.add_edge('coordinar_visita', END)
    return graph.compile()


visit_graph = build_visit_graph()
