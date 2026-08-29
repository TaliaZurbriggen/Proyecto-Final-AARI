"""Contratos HTTP para autenticación y autorización."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


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


class AuthResponse(BaseModel):
    user: AuthenticatedUser
