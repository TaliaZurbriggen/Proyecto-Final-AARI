"""Datos de contratos; las rutas privadas del bucket nunca se serializan."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractDates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha_inicio: date
    fecha_fin: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("La fecha de fin debe ser posterior a la fecha de inicio.")
        return self


class ContractCreate(ContractDates):
    inquilino_id: UUID
    propiedad_id: UUID
    contrato_anterior_id: UUID | None = None


class ContractUpdate(ContractDates):
    revision: int = Field(ge=1)


class ContractEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha_finalizacion: date
    revision: int = Field(ge=1)


class ContractDocument(BaseModel):
    id: UUID
    version: int
    nombre_archivo: str
    tamano: int
    firmado: bool
    created_at: datetime


class ContractResponse(BaseModel):
    id: UUID
    inquilino_id: UUID
    propietario_id: UUID
    propiedad_id: UUID
    inquilino_nombre: str
    propietario_nombre: str
    direccion: str
    localidad: str
    provincia: str
    fecha_inicio: date
    fecha_fin: date
    fecha_finalizacion: date | None = None
    estado: Literal["borrador", "firmado", "finalizado"]
    vigencia: str
    contrato_anterior_id: UUID | None = None
    revision: int
    created_at: datetime
    updated_at: datetime
    documentos: list[ContractDocument] = Field(default_factory=list)


class ContractsPage(BaseModel):
    items: list[ContractResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class DocumentDownload(BaseModel):
    url: str
    expires_in: int
