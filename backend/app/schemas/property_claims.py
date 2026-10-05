"""Contratos de consulta del historial de una propiedad (HU11)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.agents.classification.state import TipoGasto
from app.schemas.reclamos import ClaimHistoryItem, ClaimPropertyContext, EstadoReclamo


class PropertyClaimsFilters(BaseModel):
    page: int = Field(default=1, ge=1, le=1_000_000)
    estado: EstadoReclamo | None = None
    tipo_gasto: Literal["ordinario", "extraordinario", "expensa", "sin_clasificar"] | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.fecha_desde and self.fecha_hasta and self.fecha_desde > self.fecha_hasta:
            raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
        if self.fecha_hasta == date.max:
            raise ValueError("La fecha hasta debe ser anterior al 31/12/9999.")
        return self


class PropertyClaimSummary(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    estado: EstadoReclamo
    tipo_gasto: TipoGasto | None
    urgencia: Literal["baja", "media", "alta"]
    creado_en: datetime
    updated_at: datetime


class PropertyClaimsPage(BaseModel):
    propiedad: ClaimPropertyContext
    items: list[PropertyClaimSummary]
    total: int
    page: int
    page_size: Literal[20] = 20
    total_pages: int


class PropertyClaimDetail(PropertyClaimSummary):
    propiedad: ClaimPropertyContext
    historial: list[ClaimHistoryItem]
