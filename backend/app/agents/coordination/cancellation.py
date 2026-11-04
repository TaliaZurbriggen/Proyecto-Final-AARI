"""Subgrafo HU24: sólo enruta una cancelación ya autorizada por el dominio."""

from typing import TypedDict
from langgraph.graph import END, START, StateGraph


class CancellationState(TypedDict):
    tipo_gasto: str
    estado_resultante: str


def _return_to_choice(state):
    return {'estado_resultante': 'Autorizado' if state['tipo_gasto'] == 'extraordinario'
            else 'Pendiente de respuesta del responsable'}


builder = StateGraph(CancellationState)
builder.add_node('volver_a_eleccion_proveedor', _return_to_choice)
builder.add_edge(START, 'volver_a_eleccion_proveedor')
builder.add_edge('volver_a_eleccion_proveedor', END)
cancellation_graph = builder.compile()
