"""Carga de recursos versionados que utiliza el clasificador."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[3]
KNOWLEDGE_BASE_PATH = BACKEND_DIR / "config" / "base_conocimiento.json"
PROMPT_PATH = BACKEND_DIR / "prompts" / "prompt_clasificacion_v3.md"

# Agnóstico de versión a propósito: al pasar de v2 a v3, el header dejó de
# coincidir con un patrón que tenía "(v2)" fijo y el loader rompía al iniciar
# (AARI-112). Con \d+ el próximo bump de versión no vuelve a romper esto —
# la única fuente de verdad de qué versión se usa es PROMPT_PATH.
_PROMPT_HEADER_PATTERN = re.compile(
    r"## 2\. Prompt de sistema \(v\d+\)\s*```\s*(.*?)\s*```",
    flags=re.DOTALL,
)


def validate_confidence_threshold(value: object) -> float:
    """Valida un umbral de confianza configurable."""

    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("El umbral de confianza debe ser un número entre 0 y 1.")
    return float(value)


@lru_cache
def load_knowledge_base() -> dict[str, Any]:
    """Devuelve la base de conocimiento configurada para el agente."""

    return json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))


@lru_cache
def get_confidence_threshold() -> float:
    """Obtiene y valida el umbral configurable de escalado."""

    value = load_knowledge_base()["umbral_confianza_escalado"]["valor"]
    return validate_confidence_threshold(value)


@lru_cache
def load_prompt_template() -> str:
    """Extrae el prompt ejecutable de la documentación versionada vigente."""

    content = PROMPT_PATH.read_text(encoding="utf-8")
    match = _PROMPT_HEADER_PATTERN.search(content)
    if not match:
        raise ValueError(
            f"No se encontró el bloque de prompt ejecutable en {PROMPT_PATH.name}. "
            "Verificá que el archivo tenga un encabezado '## 2. Prompt de sistema (vN)' "
            "seguido de un bloque de código."
        )
    return match.group(1)
