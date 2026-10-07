"""Contratos de la cola y la resolución humana de clasificaciones pendientes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.classification.state import ActorResponsable, TipoGasto
from app.schemas.reclamos import ClaimHistoryItem, ClaimPropertyContext, EstadoReclamo


class EscalatedClaimItem(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    urgencia: Literal["baja", "media", "alta"]
    estado: EstadoReclamo
    creado_en: datetime
    escalado_en: datetime | None = None
    updated_at: datetime
    motivo_escalado: str | None = None
    propiedad: ClaimPropertyContext


class EscalatedClaimsPage(BaseModel):
    items: list[EscalatedClaimItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ManualDecisionRecord(BaseModel):
    id: UUID
    usuario_id: UUID
    usuario_nombre: str
    rol: Literal["operador", "administrador"]
    decidido_en: datetime
    tipo_gasto: TipoGasto
    fundamento: str
    resultado_anterior: dict[str, object]


class ClaimPhotoReference(BaseModel):
    id: UUID
    formato: str


class EscalatedClaimDetail(EscalatedClaimItem):
    inquilino_nombre: str
    fundamento_clasificacion: str | None = None
    confianza_clasificacion: float | None = None
    tipo_gasto: TipoGasto | None = None
    puede_resolver: bool
    historial: list[ClaimHistoryItem]
    fotos: list[ClaimPhotoReference]
    decisiones: list[ManualDecisionRecord]


class ManualClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_gasto: TipoGasto
    fundamento: str = Field(min_length=10, max_length=1000)
    expected_updated_at: datetime

    @field_validator("fundamento", mode="before")
    @classmethod
    def clean_reason(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("La versión del reclamo debe incluir zona horaria.")
        return value


class ManualClassificationResponse(BaseModel):
    reclamo_id: UUID
    estado: Literal["Pendiente de respuesta del responsable"]
    tipo_gasto: TipoGasto
    actor_responsable: ActorResponsable
    origen: Literal["operador", "administrador"]
    decidido_en: datetime
