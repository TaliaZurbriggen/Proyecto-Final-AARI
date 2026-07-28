"""Adaptador de Gemini para el agente de clasificación."""

import os
from typing import Protocol

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from .schemas import ModelClassification
from .state import ClassificationState

load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class ClaimClassifier(Protocol):
    """Interfaz mínima que necesita el nodo de LangGraph."""

    def invoke(self, prompt: str) -> dict[str, object]:
        """Devuelve una clasificación estructurada para el reclamo recibido."""


def build_classification_prompt(state: ClassificationState) -> str:
    """Crea el mensaje técnico; los criterios de negocio se refinan en AARI-105."""

    return f"""Clasificá el siguiente reclamo de una inmobiliaria.

Descripción: {state['descripcion']}
Urgencia declarada: {state['urgencia']}

Devolvé exclusivamente los campos definidos por el esquema: tipo_gasto
(ordinario, extraordinario o expensa), confianza entre 0 y 1, y un fundamento
breve. No incluyas datos personales ni inventes información ausente.
"""


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
        schema=ModelClassification.model_json_schema(),
        method="json_schema",
    )