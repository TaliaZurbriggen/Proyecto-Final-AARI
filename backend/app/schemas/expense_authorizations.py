"""Contratos de la decisión exclusiva del propietario (HU16)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.schemas.reclamos import ClaimHistoryItem, ClaimPropertyContext, EstadoReclamo


class ExpenseDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_updated_at: AwareDatetime


class ExpenseDecisionResult(BaseModel):
    reclamo_id: UUID
    decision: Literal["autorizar", "rechazar"]
    estado: Literal["Autorizado", "Rechazado por propietario"]
    decidido_en: datetime
    propietario_nombre: str
    repetida: bool = False
    siguiente_paso: Literal["eleccion_proveedor", "cerrado"]
    siguiente_url: str | None = None
    notificacion_estado: Literal["pendiente"] = "pendiente"


class OwnerExpenseClaim(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    estado: EstadoReclamo
    fundamento: str | None
    updated_at: datetime
    propiedad: ClaimPropertyContext
    solicitado_en: datetime
    respuesta_vence_en: datetime
    puede_decidir: bool
    decision: ExpenseDecisionResult | None = None
    historial: list[ClaimHistoryItem] = []


class OwnerExpenseClaimsPage(BaseModel):
    items: list[OwnerExpenseClaim]
    page: int
    page_size: int = 20
    total: int
    total_pages: int
