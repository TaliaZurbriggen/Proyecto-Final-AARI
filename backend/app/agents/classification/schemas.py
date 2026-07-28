"""Contratos estructurados entre Gemini y el grafo de clasificación."""

from pydantic import BaseModel, Field

from .state import TipoGasto


class ModelClassification(BaseModel):
    """Resultado mínimo que el modelo debe devolver para un reclamo."""

    tipo_gasto: TipoGasto
    confianza: float = Field(ge=0, le=1)
    fundamento: str = Field(min_length=1)