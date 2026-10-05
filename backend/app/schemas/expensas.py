"""HU14: contratos privados para reportes, seguimiento y notas de expensas."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.reclamos import ClaimPropertyContext


DeliveryStatus = Literal["pendiente", "procesando", "enviado", "fallido", "configuracion_pendiente", "historico"]


class ExpenseTenantContact(BaseModel):
    nombre: str
    email: EmailStr


class ExpenseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reclamo_id: UUID
    numero: int
    ingresado_en: datetime
    clasificado_en: datetime
    propiedad: ClaimPropertyContext
    inquilino: ExpenseTenantContact
    descripcion: str
    urgencia: Literal["baja", "media", "alta"]
    tipo_gasto: Literal["expensa"] = "expensa"
    fundamento: str
    origen: Literal["agente", "operador", "administrador"]
    confianza: float | None = Field(default=None, ge=0, le=1)


class ExpenseFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=1_000_000)
    propiedad_id: UUID | None = None
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    situacion: Literal["derivados", "pendientes", "fallidos", "historicos", "todos"] = "derivados"

    @model_validator(mode="after")
    def dates_are_valid(self):
        if self.fecha_desde and self.fecha_hasta and self.fecha_desde > self.fecha_hasta:
            raise ValueError("La fecha desde no puede ser posterior a la fecha hasta.")
        if self.fecha_hasta == date.max:
            raise ValueError("La fecha hasta debe ser anterior al 31/12/9999.")
        return self


class ExpenseListItem(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    estado: str
    creado_en: datetime
    propiedad: ClaimPropertyContext
    entrega_estado: DeliveryStatus
    intentos: int = Field(ge=0, le=3)
    error_entrega: str | None = None


class ExpensePage(BaseModel):
    items: list[ExpenseListItem]
    total: int
    page: int
    page_size: Literal[20] = 20
    total_pages: int
    pendientes: int
    fallidos: int
    sin_configuracion: int
    propiedades: list[ClaimPropertyContext]


class ExpenseDelivery(BaseModel):
    id: UUID
    canal: str
    destinatario: str
    estado: str
    intentos: int
    enviado_en: datetime | None
    creado_en: datetime
    error: str | None = None


class ExpenseNote(BaseModel):
    id: UUID
    contenido: str
    usuario_id: UUID
    autor: str
    creado_en: datetime


class ExpenseDetail(ExpenseListItem):
    reporte: ExpenseReport | None
    envios: list[ExpenseDelivery]
    notas: list[ExpenseNote]


class ExpenseNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contenido: str = Field(min_length=1, max_length=1000)

    @field_validator("contenido")
    @classmethod
    def nonempty_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Escribí una nota antes de guardarla.")
        return value


class AgencyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class AgencyEmailResponse(BaseModel):
    email: EmailStr | None
    configurado: bool
    updated_at: datetime | None = None
