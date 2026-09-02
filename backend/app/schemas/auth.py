"""Contratos HTTP para autenticación y autorización."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class AuthenticatedUser(BaseModel):
    id: UUID
    email: EmailStr
    rol: str
    primer_ingreso: bool
    perfil_id: UUID | None = None


class AuthResponse(BaseModel):
    user: AuthenticatedUser


class ChangePasswordRequest(BaseModel):
    password_actual: str = Field(min_length=1, max_length=200)
    password_nueva: str = Field(min_length=8, max_length=200)
    confirmacion_password: str = Field(min_length=8, max_length=200)

    @field_validator("password_nueva", mode="after")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not any(character.isdigit() for character in value):
            raise ValueError("La contraseña nueva debe incluir al menos un número.")
        return value

    @model_validator(mode="after")
    def validate_confirmation(self) -> "ChangePasswordRequest":
        if self.password_nueva != self.confirmacion_password:
            raise ValueError("La confirmación no coincide con la contraseña nueva.")
        return self
