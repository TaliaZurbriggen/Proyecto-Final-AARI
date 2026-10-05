"""Extensión del API sin modificar el esquema congelado de ensayos anteriores."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.clausulas_contrato import (
    ClauseReviewRequest, ContractAnalysisResponse, ContractClauseResponse,
)

AnalysisMode = Literal["ia", "literal"]


class AssistedClauseResponse(ContractClauseResponse):
    origen: AnalysisMode = "ia"


class AssistedAnalysisResponse(ContractAnalysisResponse):
    modo: AnalysisMode = "ia"
    clausulas: list[AssistedClauseResponse] = Field(default_factory=list)
    propuestas_fuente_rechazadas: list[dict[str, object]] = Field(default_factory=list)
    historial_intentos: list[dict[str, object]] = Field(default_factory=list)


class ContractAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo: AnalysisMode = "ia"


class AssistedReviewRequest(ClauseReviewRequest):
    @field_validator("resumen", "condiciones", mode="before")
    @classmethod
    def trim_review_text(cls, value):
        return value.strip() if isinstance(value, str) else value
