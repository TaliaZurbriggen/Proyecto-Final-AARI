"""Filtros opcionales de lectura; no modifican las entidades del dominio."""

from pydantic import BaseModel, Field, field_validator

from app.schemas.inquilinos import EstadoInquilino
from app.schemas.propiedades import ProvinciaArgentina, TipoPropiedad


class LocationListFilters(BaseModel):
    provincia: ProvinciaArgentina | None = None
    localidad: str | None = Field(default=None, max_length=100)

    @field_validator("localidad", mode="before")
    @classmethod
    def normalize_locality(cls, value):
        return " ".join(value.split()) or None if isinstance(value, str) else value

    def has_values(self) -> bool:
        return any(value is not None for value in self.model_dump().values())


class PropertiesListFilters(LocationListFilters):
    tipo: TipoPropiedad | None = None
    barrio: str | None = Field(default=None, max_length=100)
    propietario: str | None = Field(default=None, max_length=120)
    tiene_inquilino_activo: bool | None = None

    @field_validator("barrio", "propietario", mode="before")
    @classmethod
    def normalize_text(cls, value):
        return " ".join(value.split()) or None if isinstance(value, str) else value


class OwnersListFilters(BaseModel):
    con_inmuebles: bool | None = None

    def has_values(self) -> bool:
        return self.con_inmuebles is not None


class TenantsListFilters(LocationListFilters):
    estado: EstadoInquilino | None = None
