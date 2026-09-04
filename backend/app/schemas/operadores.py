"""Contratos públicos de gestión de operadores; nunca incluyen credenciales."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.access import AccesoResponse
from app.schemas.propietarios import PERSON_NAME_ERROR, PERSON_NAME_PATTERN


class OperadorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_completo: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)

    @field_validator("nombre_completo", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("nombre_completo")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not PERSON_NAME_PATTERN.fullmatch(value):
            raise ValueError(PERSON_NAME_ERROR)
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class OperadorResponse(BaseModel):
    id: UUID
    nombre_completo: str
    email: str
    activo: bool
    acceso: AccesoResponse | None = None
    created_at: datetime


class OperadoresPage(BaseModel):
    items: list[OperadorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class OperadorDesactivadoResponse(BaseModel):
    operador: OperadorResponse
    reclamos_liberados: int = Field(ge=0)
