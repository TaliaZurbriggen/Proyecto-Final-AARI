"""Endpoints y dependencias reutilizables de autenticación."""

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.security import (
    COOKIE_NAME,
    InvalidSessionError,
    access_token_minutes,
    cookie_secure,
    create_access_token,
    decode_access_token,
)
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.schemas.auth import AuthResponse, AuthenticatedUser, LoginRequest
from app.services.auth_service import (
    AccountLockedError,
    AuthService,
    InactiveAccountError,
    InvalidCredentialsError,
)


router = APIRouter(prefix="/auth", tags=["autenticación"])


def get_auth_service() -> AuthService:
    return AuthService(SqlAlchemyUsuariosRepository())


def _unauthorized(message: str = "La sesión no es válida o venció.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": message},
    )


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    if not session_token:
        raise _unauthorized()
    try:
        payload = decode_access_token(session_token)
        return service.get_active_user(UUID(str(payload["sub"])))
    except (InvalidSessionError, InvalidCredentialsError, InactiveAccountError, ValueError):
        raise _unauthorized() from None


def require_roles(*roles: str) -> Callable[..., AuthenticatedUser]:
    def dependency(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": "No tenés permiso para acceder a este recurso.",
                },
            )
        return user

    return dependency


require_admin = require_roles("administrador")


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> AuthResponse:
    try:
        user = service.login(payload)
    except InvalidCredentialsError as error:
        raise _unauthorized("El email o la contraseña son incorrectos.") from error
    except AccountLockedError as error:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "code": "account_locked",
                "message": "La cuenta está bloqueada. Intentá nuevamente en 15 minutos.",
            },
        ) from error
    except InactiveAccountError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "account_inactive",
                "message": "La cuenta está desactivada.",
            },
        ) from error

    token = create_access_token(
        user_id=str(user.id),
        role=user.rol,
        first_login=user.primer_ingreso,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        max_age=access_token_minutes() * 60,
        path="/",
    )
    return AuthResponse(user=user)


@router.get("/me", response_model=AuthResponse)
def me(user: AuthenticatedUser = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
