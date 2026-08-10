"""Adaptador de Gemini para el agente de clasificaci?n."""

import json
import os
from typing import Protocol

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from .resources import (
    get_confidence_threshold,
    load_knowledge_base,
    load_prompt_template,
    validate_confidence_threshold,
)
from .schemas import ModelClassification
from .state import ClassificationState

load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class ClaimClassifier(Protocol):
    """Interfaz m?nima que necesita el nodo de LangGraph."""

    def invoke(self, prompt: str) -> dict[str, object]:
        """Devuelve una clasificaci?n estructurada para el reclamo recibido."""


def build_classification_prompt(
    state: ClassificationState,
    confidence_threshold: float | None = None,
) -> str:
    """Construye el prompt vigente con los recursos externos al código."""

    threshold = (
        validate_confidence_threshold(confidence_threshold)
        if confidence_threshold is not None
        else get_confidence_threshold()
    )
    replacements = {
        "{{BASE_CONOCIMIENTO_JSON}}": json.dumps(
            load_knowledge_base(), ensure_ascii=False, separators=(",", ":")
        ),
        "{{descripcion}}": state["descripcion"],
        "{{urgencia}}": state["urgencia"],
        "{{rubro_declarado}}": state.get("rubro_declarado") or "no disponible",
        "{{clausulas_contrato}}": json.dumps(
            state.get("clausulas_contrato", []), ensure_ascii=False
        ),
        "{{umbral_confianza}}": f"{threshold:.2f}",
    }
    prompt = load_prompt_template()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt


def get_gemini_classifier() -> ClaimClassifier:
    """Configura Gemini con salida JSON validable por el grafo."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Definila en backend/.env sin subirla a Git."
        )

    model = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        google_api_key=api_key,
        temperature=0,
    )
    return model.with_structured_output(
        schema=ModelClassification,
        method="json_schema",
    )
