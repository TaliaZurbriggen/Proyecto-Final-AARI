"""Contratos autenticados HU17. No aceptar identidad desde el formulario."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.schemas.reclamos import ClaimPropertyContext, EstadoReclamo


class ProviderChoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    solicitud_id: UUID
    expected_updated_at: AwareDatetime
    tipo_proveedor: Literal["fidelizado", "propio"]


class ProviderChoiceResult(BaseModel):
    reclamo_id: UUID
    solicitud_id: UUID
    tipo_proveedor: Literal["fidelizado", "propio"]
    estado: EstadoReclamo
    siguiente_paso: Literal["solicitar_presupuestos", "registrar_proveedor_propio"]
    decidido_en: datetime
    actor_nombre: str
    repetida: bool = False


class ProviderChoiceDetail(BaseModel):
    reclamo_id: UUID
    numero: int
    descripcion: str
    estado: EstadoReclamo
    propiedad: ClaimPropertyContext
    actor_tipo: Literal["inquilino", "propietario"]
    solicitud_id: UUID
    solicitado_en: datetime
    respuesta_vence_en: datetime
    updated_at: datetime
    puede_elegir: bool
    decision: ProviderChoiceResult | None = None
