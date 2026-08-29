"""Creación y validación de tokens de sesión de AARI."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError


ALGORITHM = "HS256"
COOKIE_NAME = "aari_session"


class InvalidSessionError(Exception):
    """El token no existe, venció o no pudo validarse."""


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET debe tener al menos 32 caracteres.")
    return secret


def access_token_minutes() -> int:
    raw_value = os.getenv("JWT_EXPIRE_MINUTES", "480")
    try:
        return max(1, int(raw_value))
    except ValueError as error:
        raise RuntimeError("JWT_EXPIRE_MINUTES debe ser un número entero.") from error


def create_access_token(
    *,
    user_id: str,
    role: str,
    first_login: bool,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": user_id,
        "rol": role,
        "primer_ingreso": first_login,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=access_token_minutes()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
    except (InvalidTokenError, RuntimeError) as error:
        raise InvalidSessionError from error

    if not payload.get("sub") or not payload.get("rol"):
        raise InvalidSessionError
    return payload


def cookie_secure() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() not in {
        "development",
        "local",
        "test",
    }
