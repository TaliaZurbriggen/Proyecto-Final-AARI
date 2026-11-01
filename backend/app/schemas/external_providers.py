"""HU18: contacto externo, sin identidad ni permisos elegibles por el cliente."""

from datetime import datetime
import re
import unicodedata
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.reclamos import ClaimPropertyContext, EstadoReclamo


def normalize_external_name(value: str) -> str:
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not 3 <= len(value) <= 120 or not all(c.isalpha() or c in " '-’" for c in value) or not any(c.isalpha() for c in value):
        raise ValueError("Ingresá un nombre completo de 3 a 120 caracteres, sin números ni símbolos.")
    return value


def normalize_external_phone(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"\+?[0-9 ()-]+", value):
        raise ValueError("Ingresá un teléfono de 8 a 15 dígitos, sin letras.")
    normalized = re.sub(r"[ +()-]", "", value)
    if not 8 <= len(normalized) <= 15:
        raise ValueError("El teléfono debe tener entre 8 y 15 dígitos.")
    return normalized


class ExternalProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    eleccion_id: UUID
    expected_updated_at: AwareDatetime
    nombre: str = Field(max_length=500)
    telefono: str = Field(max_length=100)

    @field_validator("nombre")
    @classmethod
    def name(cls, value):
        return normalize_external_name(value)

    @field_validator("telefono")
    @classmethod
    def phone(cls, value):
        return normalize_external_phone(value)


class ExternalProviderRecord(BaseModel):
    id: UUID
    nombre: str
    telefono: str
    created_at: datetime
    eleccion_id: UUID | None = None
    actor_nombre: str | None = None


class ExternalProviderDetail(BaseModel):
    reclamo_id: UUID
    numero: int
    descripcion: str
    estado: EstadoReclamo
    propiedad: ClaimPropertyContext
    eleccion_id: UUID | None = None
    updated_at: datetime
    puede_registrar: bool
    motivo_bloqueo: str | None = None
    registro: ExternalProviderRecord | None = None
    registros: list[ExternalProviderRecord] = Field(default_factory=list)


class ExternalProviderResult(BaseModel):
    reclamo_id: UUID
    estado: EstadoReclamo
    registro: ExternalProviderRecord
    repetida: bool = False
