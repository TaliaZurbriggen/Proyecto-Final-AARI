"""Adaptador estructurado de Gemini para cláusulas contractuales."""

import os
import re
from pathlib import Path
from typing import Protocol
import unicodedata

from langchain_google_genai import ChatGoogleGenerativeAI

from app.schemas.clausulas_contrato import (
    ExtractedClause, ExtractedClauseBatch, RejectedClause,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt_extraccion_clausulas_v4.md"
PROMPT_VERSION = "v4"
EXTRACTOR_VERSION = "hu30-v4"
DEFAULT_MODEL = "gemini-3.5-flash"


class ClauseModel(Protocol):
    def invoke(self, prompt: str) -> object: ...


def build_clause_prompt(text: str) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{{TEXTO_CONTRATO}}", text)


def get_clause_model() -> ClauseModel:
    enabled = os.getenv("CONTRACT_ANALYSIS_EXTERNAL_ENABLED", "false").lower()
    if enabled not in {"1", "true", "yes"}:
        raise RuntimeError(
            "El análisis externo está deshabilitado hasta habilitar el tratamiento de contratos."
        )
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("El análisis con Gemini no está configurado.")
    model = ChatGoogleGenerativeAI(
        model=os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL),
        google_api_key=key,
        temperature=0,
    )
    # El endpoint generateContent rechazó el esquema JSON nativo de esta salida
    # con INVALID_ARGUMENT. Tool calling conserva la estructura tipada y deja la
    # validación final en Pydantic sin transmitir ese esquema como response schema.
    return model.with_structured_output(ExtractedClauseBatch, method="function_calling")


def parse_batch(value: object) -> ExtractedClauseBatch:
    return value if isinstance(value, ExtractedClauseBatch) else ExtractedClauseBatch.model_validate(value)


def normalize_evidence(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").translate(str.maketrans({
        "\u00ad": "", "“": '"', "”": '"', "„": '"', "’": "'",
        "–": "-", "—": "-",
    }))
    normalized = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def validate_evidence(
    batch: ExtractedClauseBatch,
    pages: dict[int, str],
) -> tuple[list[ExtractedClause], list[RejectedClause], list[str]]:
    valid: list[ExtractedClause] = []
    rejected: list[RejectedClause] = []
    incidents: list[str] = []
    for index, clause in enumerate(batch.clausulas, start=1):
        invalid = []
        reasons = []
        for evidence in clause.evidencias:
            page_text = pages.get(evidence.pagina, "")
            if not page_text:
                invalid.append(evidence)
                reasons.append(f"la página {evidence.pagina} no está disponible")
            elif normalize_evidence(evidence.texto) not in normalize_evidence(page_text):
                invalid.append(evidence)
                reasons.append(f"el fragmento de la página {evidence.pagina} no es literal")
        if invalid:
            reason = "; ".join(dict.fromkeys(reasons)) + "."
            rejected.append(RejectedClause(
                ordinal=index,
                propuesta=clause,
                motivo=reason,
                evidencias_invalidas=invalid,
            ))
            incidents.append(f"La propuesta {index} requiere revisión de evidencia: {reason}")
            continue
        valid.append(clause)
    return valid, rejected, incidents
