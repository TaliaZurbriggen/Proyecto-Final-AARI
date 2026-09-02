"""Contratos HTTP para la gestión de inquilinos."""

import re
from datetime import datetime
from enum import Enum
from math import ceil
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.access import AccesoResponse


PERSON_NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '\-’][^\W\d_]+)*$", re.UNICODE)
PERSON_NAME_ERROR = (
    "Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones."
)


class EstadoInquilino(str, Enum):
    """Estados derivados de la asociación actual con una propiedad."""

    ACTIVO = "activo"
    SIN_PROPIEDAD_ASIGNADA = "sin_propiedad_asignada"


class InquilinoContactInput(BaseModel):
    """Datos personales compartidos por alta y edición."""

    nombre_completo: str = Field(min_length=2, max_length=120)
    dni: str = Field(pattern=r"^[0-9]{7,8}$")
    email: EmailStr
    telefono: str = Field(min_length=6, max_length=30)

    @field_validator("nombre_completo", "dni", "telefono", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.split())

    @field_validator("nombre_completo", mode="after")
    @classmethod
    def validate_person_name(cls, value: str) -> str:
        if not PERSON_NAME_PATTERN.fullmatch(value):
            raise ValueError(PERSON_NAME_ERROR)
        return value

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class InquilinoCreate(InquilinoContactInput):
    """Alta de un inquilino con una propiedad disponible obligatoria."""

    propiedad_id: UUID


class InquilinoUpdate(InquilinoContactInput):
    """Edición de datos y reasignación opcional de una propiedad."""

    propiedad_id: UUID | None = None


class PropiedadInquilinoResumen(BaseModel):
    """Ubicación mínima mostrada junto al inquilino."""

    id: UUID
    direccion: str
    provincia: str
    localidad: str
    barrio: str | None = None
    tipo: str
    piso: int | None = None
    numero: str | None = None


class InquilinoResponse(InquilinoContactInput):
    """Representación pública de un inquilino y su asociación actual."""

    id: UUID
    propiedad: PropiedadInquilinoResumen | None = None
    estado: EstadoInquilino
    cantidad_reclamos: int = Field(ge=0)
    acceso: AccesoResponse | None = None
    created_at: datetime
    updated_at: datetime


class InquilinosPage(BaseModel):
    """Página estable para el listado administrativo."""

    items: list[InquilinoResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)

    @classmethod
    def build(
        cls,
        *,
        items: list[dict[str, object]],
        page: int,
        page_size: int,
        total: int,
    ) -> "InquilinosPage":
        return cls(
            items=[InquilinoResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
