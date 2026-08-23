"""Contratos HTTP para la gestión de propiedades."""

from datetime import datetime
from enum import Enum
from math import ceil
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class TipoPropiedad(str, Enum):
    """Tipos de inmueble admitidos por el dominio."""

    DEPARTAMENTO = "departamento"
    CASA = "casa"
    LOCAL = "local"
    OTRO = "otro"


class ProvinciaArgentina(str, Enum):
    """Jurisdicciones argentinas disponibles para ubicar un inmueble."""

    BUENOS_AIRES = "Buenos Aires"
    CABA = "Ciudad Autónoma de Buenos Aires"
    CATAMARCA = "Catamarca"
    CHACO = "Chaco"
    CHUBUT = "Chubut"
    CORDOBA = "Córdoba"
    CORRIENTES = "Corrientes"
    ENTRE_RIOS = "Entre Ríos"
    FORMOSA = "Formosa"
    JUJUY = "Jujuy"
    LA_PAMPA = "La Pampa"
    LA_RIOJA = "La Rioja"
    MENDOZA = "Mendoza"
    MISIONES = "Misiones"
    NEUQUEN = "Neuquén"
    RIO_NEGRO = "Río Negro"
    SALTA = "Salta"
    SAN_JUAN = "San Juan"
    SAN_LUIS = "San Luis"
    SANTA_CRUZ = "Santa Cruz"
    SANTA_FE = "Santa Fe"
    SANTIAGO_DEL_ESTERO = "Santiago del Estero"
    TIERRA_DEL_FUEGO = "Tierra del Fuego, Antártida e Islas del Atlántico Sur"
    TUCUMAN = "Tucumán"


class PropiedadInput(BaseModel):
    """Campos editables compartidos por el alta y la modificación."""

    direccion: str = Field(min_length=2, max_length=200)
    provincia: ProvinciaArgentina
    localidad: str = Field(min_length=2, max_length=100)
    barrio: str | None = Field(default=None, min_length=2, max_length=100)
    tipo: TipoPropiedad
    piso: int | None = None
    numero: str | None = Field(default=None, max_length=30)
    propietario_id: UUID

    @field_validator("direccion", "localidad", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.split())

    @field_validator("barrio", "numero", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("direccion", "localidad", "barrio")
    @classmethod
    def require_location_letter(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None or any(character.isalpha() for character in value):
            return value
        messages = {
            "direccion": "La dirección debe incluir el nombre de la calle o ruta.",
            "localidad": "La localidad debe contener al menos una letra.",
            "barrio": "El barrio debe contener al menos una letra.",
        }
        raise ValueError(messages[info.field_name])

    @field_validator("provincia", mode="before")
    @classmethod
    def normalize_province(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        for province in ProvinciaArgentina:
            if province.value.casefold() == normalized.casefold():
                return province.value
        return normalized

    @model_validator(mode="after")
    def clear_unit_for_non_apartment(self) -> "PropiedadInput":
        if self.tipo != TipoPropiedad.DEPARTAMENTO:
            self.piso = None
            self.numero = None
        return self


class PropiedadCreate(PropiedadInput):
    """Solicitud de alta de una propiedad."""


class PropiedadUpdate(PropiedadInput):
    """Solicitud de reemplazo de los datos editables de una propiedad."""


class PropietarioResumen(BaseModel):
    """Identidad mínima del propietario asociado."""

    id: UUID
    nombre_completo: str


class PropiedadResponse(BaseModel):
    """Representación pública de una propiedad."""

    id: UUID
    direccion: str
    provincia: ProvinciaArgentina
    localidad: str
    barrio: str | None = None
    tipo: TipoPropiedad
    piso: int | None = None
    numero: str | None = None
    propietario: PropietarioResumen
    cantidad_reclamos: int = Field(ge=0)
    tiene_inquilino_activo: bool
    created_at: datetime
    updated_at: datetime


class PropiedadesPage(BaseModel):
    """Página estable para listados del frontend."""

    items: list[PropiedadResponse]
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
    ) -> "PropiedadesPage":
        return cls(
            items=[PropiedadResponse.model_validate(item) for item in items],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )
