"""Contratos HTTP para la gestión de propietarios."""

import re
from datetime import datetime
from math import ceil
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.access import AccesoResponse


PERSON_NAME_PATTERN = re.compile(r"^[^\W\d_]+(?:[ '\-’][^\W\d_]+)*$", re.UNICODE)
PERSON_NAME_ERROR = (
    "Ingresá un nombre válido usando solo letras, espacios, apóstrofes o guiones."
)


class PropietarioInput(BaseModel):
    """Campos editables compartidos por el alta y la modificación."""

    nombre_completo: str = Field(min_length=2, max_length=120)
    dni: str = Field(pattern=r"^[0-9]{7,8}$")
    email: EmailStr
    telefono: str = Field(min_length=6, max_length=30)

    @field_validator("nombre_completo", "dni", "telefono", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

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


class PropietarioCreate(PropietarioInput):
    """Solicitud de alta de un propietario."""


class PropietarioUpdate(PropietarioInput):
    """Solicitud de reemplazo de los datos editables de un propietario."""


class PropiedadResumen(BaseModel):
    """Datos mínimos de una propiedad asociada para la vista de detalle."""

    id: UUID
    direccion: str
    provincia: str
    localidad: str
    barrio: str | None = None
    tipo: str
    piso: int | None = None
    numero: str | None = None


class PropietarioResponse(PropietarioInput):
    """Representación pública resumida de un propietario."""

    id: UUID
    cantidad_inmuebles: int = Field(ge=0)
    acceso: AccesoResponse | None = None
    created_at: datetime
    updated_at: datetime


class PropietarioDetailResponse(PropietarioResponse):
    """Detalle de propietario con sus propiedades asociadas."""

    propiedades: list[PropiedadResumen]


class PropietariosPage(BaseModel):
    """Página estable para listados del frontend."""

    items: list[PropietarioResponse]
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
    ) -> "PropietariosPage":
        return cls(
            items=[PropietarioResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
