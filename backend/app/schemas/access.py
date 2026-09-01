"""Contratos compartidos para la entrega de credenciales de acceso."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EstadoEntregaAcceso(str, Enum):
    """Estados persistidos del correo de bienvenida."""

    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    FALLIDO = "fallido"


class AccesoResponse(BaseModel):
    """Estado público del acceso vinculado a una persona."""

    estado: EstadoEntregaAcceso
    intentos: int = Field(ge=0)
    primer_ingreso: bool
    ultimo_error: str | None = None
    enviado_en: datetime | None = None
