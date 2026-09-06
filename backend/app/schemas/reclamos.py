"""Contratos HTTP y de aplicación para crear y clasificar reclamos."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.agents.classification.state import MotivoEscalado, TipoGasto


EstadoPersistido = Literal["Clasificado", "Escalado"]


class ClaimPropertyContext(BaseModel):
    """Unidad vinculada al inquilino que inicia el reclamo."""

    id: UUID
    direccion: str
    provincia: str
    localidad: str
    barrio: str | None = None
    tipo: str
    piso: int | None = None
    numero: str | None = None


class ClaimContextResponse(BaseModel):
    """Contexto visible antes de confirmar un alta."""

    inquilino_nombre: str
    inquilino_email: str
    propiedad: ClaimPropertyContext


class ClaimCreatedResponse(BaseModel):
    """Confirmación inmediata de que el reclamo quedó persistido."""

    id: UUID
    numero: int
    estado: Literal["Recibido"]
    creado_en: datetime
    notificacion_estado: Literal["pendiente"] = "pendiente"
    fotos_adjuntas: int


class AgentClassificationResult(BaseModel):
    """Resultado del grafo antes de guardarlo en la base de datos."""

    tipo_gasto: TipoGasto | None
    confianza: float | None = Field(default=None, ge=0, le=1)
    fundamento: str | None = None
    debe_escalar: bool
    motivo_escalado: MotivoEscalado | None
    estado_clasificacion: Literal["clasificado", "escalado"]

    @model_validator(mode="after")
    def validate_contract(self) -> "AgentClassificationResult":
        """Evita persistir resultados contradictorios del grafo."""

        if self.debe_escalar:
            if self.tipo_gasto is not None or self.motivo_escalado is None:
                raise ValueError("Un escalado requiere tipo_gasto nulo y motivo_escalado.")
            if self.estado_clasificacion != "escalado":
                raise ValueError("Un escalado debe tener estado_clasificacion escalado.")
        elif self.tipo_gasto is None or self.motivo_escalado is not None:
            raise ValueError("Una clasificación requiere tipo_gasto y no admite motivo.")
        elif self.estado_clasificacion != "clasificado":
            raise ValueError("Una clasificación debe tener estado_clasificacion clasificado.")
        return self


class ClaimClassificationResponse(BaseModel):
    """Respuesta pública luego de persistir una clasificación."""

    reclamo_id: UUID
    estado: EstadoPersistido
    tipo_gasto: TipoGasto | None
    confianza: float | None
    fundamento: str | None
    debe_escalar: bool
    motivo_escalado: MotivoEscalado | None
    origen: Literal["agente"] = "agente"
