"""Contratos HU32: nunca devolver tokens de invitación al administrador."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ProviderInvitationRequest(BaseModel):
    email: EmailStr = Field(max_length=254)
    request_id: UUID

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ProviderActivationRequest(BaseModel):
    token: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    password_nueva: str = Field(min_length=8, max_length=200, repr=False)
    confirmacion_password: str = Field(min_length=8, max_length=200, repr=False)

    @model_validator(mode="after")
    def valid_password(self):
        if len(self.password_nueva.encode("utf-8")) > 72:
            raise ValueError("La contraseña es demasiado larga (máximo 72 bytes).")
        if not any(c.isdigit() for c in self.password_nueva):
            raise ValueError("La contraseña debe incluir al menos un número.")
        if self.password_nueva != self.confirmacion_password:
            raise ValueError("La confirmación no coincide con la contraseña.")
        return self


class ProviderAccessResponse(BaseModel):
    proveedor_id: UUID
    email: EmailStr | None = None
    estado: str
    envio_estado: str | None = None
    vence_en: datetime | None = None
    ultimo_error: str | None = None
    puede_invitar: bool


class ProviderProfileResponse(BaseModel):
    proveedor_id: UUID
    nombre_razon_social: str
    email: EmailStr
    solicitudes_disponibles: bool = False
    aviso_integracion: str = "La bandeja se habilitará al integrar las solicitudes de presupuesto de HU19."
