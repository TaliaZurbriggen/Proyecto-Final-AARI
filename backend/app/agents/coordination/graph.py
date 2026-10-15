"""Grafo de espera/reanudación. Las HU de dominio realizan las decisiones."""

from langgraph.graph import END, START, StateGraph

from .state import CoordinationSnapshot, CoordinationState, DomainContext, stage_for


STAGES = (
    "esperando_autorizacion", "esperando_eleccion_proveedor",
    "esperando_presupuestos", "esperando_seleccion_presupuesto",
    "esperando_disponibilidad", "visita_programada", "derivado_externo",
    "rechazado", "expirada", "intervencion_manual", "finalizado",
)


def _project(state: CoordinationState) -> dict:
    snapshot = CoordinationSnapshot.model_validate(state["contexto"])
    domain = DomainContext.model_validate(state["dominio"])
    if snapshot.reclamo_id != domain.reclamo_id:
        raise ValueError("El contexto no corresponde al reclamo.")
    recent = (snapshot.eventos_recientes + [state["evento_id"]])[-20:]
    return {"contexto": snapshot.model_copy(update={
        "dominio": domain, "etapa": stage_for(domain), "eventos_recientes": recent,
    }).model_dump(mode="json")}


def _route(state: CoordinationState) -> str:
    return state["contexto"]["etapa"]


def _wait(state: CoordinationState) -> dict:
    # Fin del turno, no del reclamo. El próximo evento retoma el mismo thread.
    return {}


def build_coordination_graph(checkpointer):
    builder = StateGraph(CoordinationState)
    builder.add_node("proyectar_dominio", _project)
    builder.add_edge(START, "proyectar_dominio")
    for stage in STAGES:
        builder.add_node(stage, _wait)
        builder.add_edge(stage, END)
    builder.add_conditional_edges("proyectar_dominio", _route, {s: s for s in STAGES})
    return builder.compile(checkpointer=checkpointer)
