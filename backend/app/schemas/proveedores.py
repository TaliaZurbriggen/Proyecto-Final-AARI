"""Contratos HTTP para la gestión administrativa de proveedores."""

import re
from datetime import datetime, time
from math import ceil
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.schemas.propiedades import ProvinciaArgentina


PHONE_ALLOWED_PATTERN = re.compile(r"^\+?[0-9\s().-]+$")


def normalize_words(value: str) -> str:
    """Recorta y unifica espacios internos sin alterar tildes ni mayúsculas."""

    return " ".join(value.split())


def normalize_phone(value: str) -> str:
    """Convierte una escritura amigable al formato internacional de WhatsApp."""

    normalized = value.strip()
    if not PHONE_ALLOWED_PATTERN.fullmatch(normalized):
        raise ValueError("Ingresá un teléfono usando números, espacios o guiones.")
    if not normalized.startswith("+"):
        raise ValueError("Incluí el código de país, por ejemplo +54.")
    digits = "".join(character for character in normalized if character.isdigit())
    if not 8 <= len(digits) <= 15:
        raise ValueError("Ingresá un teléfono internacional válido de 8 a 15 números.")
    return f"+{digits}"


class CoberturaInput(BaseModel):
    """Localidad completa o conjunto explícito de barrios cubiertos."""

    provincia: ProvinciaArgentina
    localidad: str = Field(min_length=2, max_length=100)
    cubre_toda_localidad: bool = True
    barrios: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("localidad", mode="before")
    @classmethod
    def normalize_locality(cls, value: object) -> object:
        return normalize_words(value) if isinstance(value, str) else value

    @field_validator("localidad")
    @classmethod
    def require_locality_letter(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("La localidad debe contener al menos una letra.")
        return value

    @field_validator("provincia", mode="before")
    @classmethod
    def normalize_province(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_words(value)
        for province in ProvinciaArgentina:
            if province.value.casefold() == normalized.casefold():
                return province.value
        return normalized

    @field_validator("barrios", mode="before")
    @classmethod
    def normalize_neighborhoods(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_neighborhood in value:
            if not isinstance(raw_neighborhood, str):
                normalized.append(raw_neighborhood)
                continue
            neighborhood = normalize_words(raw_neighborhood)
            if not neighborhood:
                continue
            key = neighborhood.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(neighborhood)
        return normalized

    @field_validator("barrios")
    @classmethod
    def validate_neighborhoods(cls, value: list[str]) -> list[str]:
        for neighborhood in value:
            if not 2 <= len(neighborhood) <= 100:
                raise ValueError("Cada barrio debe tener entre 2 y 100 caracteres.")
            if not any(character.isalpha() for character in neighborhood):
                raise ValueError("Cada barrio debe contener al menos una letra.")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "CoberturaInput":
        if self.cubre_toda_localidad and self.barrios:
            raise ValueError(
                "No cargues barrios cuando el proveedor cubre toda la localidad."
            )
        if not self.cubre_toda_localidad and not self.barrios:
            raise ValueError("Ingresá al menos un barrio o marcá toda la localidad.")
        return self


class ProveedorInput(BaseModel):
    """Campos editables compartidos por alta y modificación."""

    nombre_razon_social: str = Field(min_length=2, max_length=150)
    matricula: str | None = Field(default=None, max_length=80)
    telefono: str
    activo: bool = True
    hora_inicio: time | None = None
    hora_fin: time | None = None
    especialidad_ids: list[UUID] = Field(default_factory=list, max_length=50)
    especialidades_personalizadas: list[str] = Field(default_factory=list, max_length=20)
    coberturas: list[CoberturaInput] = Field(min_length=1, max_length=30)

    @field_validator("nombre_razon_social", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return normalize_words(value) if isinstance(value, str) else value

    @field_validator("nombre_razon_social")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("El nombre o razón social debe contener al menos una letra.")
        return value

    @field_validator("matricula", mode="before")
    @classmethod
    def normalize_registration(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_words(value).upper()
        return normalized or None

    @field_validator("telefono", mode="before")
    @classmethod
    def normalize_whatsapp_phone(cls, value: object) -> object:
        return normalize_phone(value) if isinstance(value, str) else value

    @field_validator("especialidad_ids", mode="before")
    @classmethod
    def deduplicate_specialty_ids(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return list(dict.fromkeys(value))

    @field_validator("especialidades_personalizadas", mode="before")
    @classmethod
    def normalize_custom_specialties(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_name in value:
            if not isinstance(raw_name, str):
                normalized.append(raw_name)
                continue
            name = normalize_words(raw_name).lower()
            if not name:
                continue
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(name)
        return normalized

    @field_validator("especialidades_personalizadas")
    @classmethod
    def validate_custom_specialties(cls, value: list[str]) -> list[str]:
        for specialty in value:
            if not 2 <= len(specialty) <= 80:
                raise ValueError(
                    "Cada especialidad debe tener entre 2 y 80 caracteres."
                )
            if not any(character.isalpha() for character in specialty):
                raise ValueError("Cada especialidad debe contener al menos una letra.")
        return value

    @field_validator("coberturas")
    @classmethod
    def prevent_duplicate_locations(
        cls, value: list[CoberturaInput]
    ) -> list[CoberturaInput]:
        locations: set[tuple[str, str]] = set()
        for coverage in value:
            key = (coverage.provincia.value.casefold(), coverage.localidad.casefold())
            if key in locations:
                raise ValueError(
                    "Cada provincia y localidad debe aparecer una sola vez."
                )
            locations.add(key)
        return value

    @model_validator(mode="after")
    def validate_specialties_and_schedule(self) -> "ProveedorInput":
        if not self.especialidad_ids and not self.especialidades_personalizadas:
            raise ValueError("Seleccioná o creá al menos una especialidad.")
        if (self.hora_inicio is None) != (self.hora_fin is None):
            raise ValueError("Completá juntas la hora de inicio y la hora de fin.")
        if self.hora_inicio is not None and self.hora_fin is not None:
            if self.hora_fin <= self.hora_inicio:
                raise ValueError("La hora de fin debe ser posterior a la de inicio.")
        return self


class ProveedorCreate(ProveedorInput):
    """Solicitud de alta de un proveedor."""


class ProveedorUpdate(ProveedorInput):
    """Reemplazo de los datos editables de un proveedor."""


class ProveedorEstadoUpdate(BaseModel):
    """Cambio explícito de elegibilidad general."""

    activo: bool


class EspecialidadResponse(BaseModel):
    id: UUID
    nombre: str


class CoberturaResponse(CoberturaInput):
    id: UUID


class ProveedorResponse(BaseModel):
    id: UUID
    nombre_razon_social: str
    matricula: str | None = None
    telefono: str
    activo: bool
    hora_inicio: time | None = None
    hora_fin: time | None = None
    especialidades: list[EspecialidadResponse]
    coberturas: list[CoberturaResponse]
    created_at: datetime
    updated_at: datetime


class ProveedoresPage(BaseModel):
    items: list[ProveedorResponse]
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
    ) -> "ProveedoresPage":
        return cls(
            items=[ProveedorResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
