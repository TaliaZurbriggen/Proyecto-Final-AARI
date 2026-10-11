"""HU15: grafo separado del clasificador de gastos, con adaptador inyectable."""

import json
import os
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from app.agents.classification.llm import DEFAULT_GEMINI_MODEL

PROMPT_VERSION = "especialidad_proveedores_v1"
PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "prompt_especialidad_proveedores_v1.md"


class SpecialtyResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    especialidad_id: UUID | None
    fundamento: str = Field(min_length=1, max_length=500)
    evidencia: str = Field(max_length=500)


class CandidateAgentState(TypedDict, total=False):
    descripcion: str
    tipo_id: UUID | None
    catalogo: list[dict]
    especialidad_id: UUID | None
    motivo: str
    fuente: str
    modelo: str | None
    prompt_version: str | None
    busqueda: object


def get_specialty_resolver():
    # Se construye sólo si el reclamo no tiene especialidad. Nunca reintenta
    # silenciosamente una llamada ni envía contratos, contactos o fotografías.
    from langchain_google_genai import ChatGoogleGenerativeAI

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Falta la configuración del modelo.")
    return ChatGoogleGenerativeAI(
        model=os.getenv("PROVIDER_SPECIALTY_MODEL") or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        google_api_key=key, temperature=0, timeout=30, max_retries=0,
    ).with_structured_output(SpecialtyResolution, method="json_schema")


def build_specialty_prompt(description, catalog):
    return PROMPT_PATH.read_text(encoding="utf-8") + "\nDATOS_JSON:\n" + json.dumps(
        {"descripcion": description, "catalogo": [{"id": str(s["id"]), "nombre": s["nombre"]} for s in catalog]},
        ensure_ascii=False,
    )


def build_provider_candidates_graph(search, *, resolver=None, external_enabled=False):
    """Resolver especialidad -> filtrar padrón -> resultado, sin contratar.

    `search` es el puerto de persistencia transaccional; en producción se invoca
    desde el worker, no desde el navegador ni una función de prueba aislada.
    """
    def resolve(state):
        known = {UUID(str(item["id"])) for item in state["catalogo"]}
        if state.get("tipo_id") is not None:
            specialty = UUID(str(state["tipo_id"]))
            return {"especialidad_id": specialty if specialty in known else None,
                    "fuente": "registrada", "motivo": "Especialidad registrada." if specialty in known else "La especialidad registrada ya no existe.",
                    "modelo": None, "prompt_version": None}
        if not known:
            return {"especialidad_id": None, "fuente": "revision", "motivo": "No hay especialidades en el catálogo."}
        if resolver is None and not external_enabled:
            return {"especialidad_id": None, "fuente": "revision", "motivo": "Falta especialidad; la consulta externa no está habilitada."}
        try:
            model = resolver if resolver is not None else get_specialty_resolver()
            raw = model.invoke(build_specialty_prompt(state["descripcion"], state["catalogo"]))
            result = SpecialtyResolution.model_validate(raw)
            if result.especialidad_id is not None:
                if result.especialidad_id not in known or not result.evidencia.strip():
                    raise ValueError("ID o evidencia inválidos.")
                if " ".join(result.evidencia.casefold().split()) not in " ".join(state["descripcion"].casefold().split()):
                    raise ValueError("La evidencia no está en la descripción.")
            return {"especialidad_id": result.especialidad_id, "fuente": "modelo",
                    "motivo": "Especialidad identificada por el agente." if result.especialidad_id else "El reclamo no permite identificar una única especialidad del catálogo.",
                    "modelo": os.getenv("PROVIDER_SPECIALTY_MODEL") or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
                    "prompt_version": PROMPT_VERSION}
        except Exception:
            # No persistir la excepción: puede incluir prompt o credenciales.
            return {"especialidad_id": None, "fuente": "revision", "motivo": "No se obtuvo una respuesta válida del modelo; requiere revisión.",
                    "modelo": None, "prompt_version": PROMPT_VERSION}

    def find(state):
        return {"busqueda": search(state)}

    graph = StateGraph(CandidateAgentState)
    graph.add_node("identificar_especialidad", resolve)
    graph.add_node("buscar_proveedores_compatibles", find)
    graph.add_edge(START, "identificar_especialidad")
    graph.add_edge("identificar_especialidad", "buscar_proveedores_compatibles")
    graph.add_edge("buscar_proveedores_compatibles", END)
    return graph.compile()
