"""Dobles compartidos para mantener aisladas las pruebas de módulos administrativos."""

from uuid import UUID

import pytest

from app.api.auth import require_admin
from app.main import app
from app.schemas.auth import AuthenticatedUser


@pytest.fixture(autouse=True)
def authenticated_admin_for_existing_module_tests():
    """Las pruebas de cada CRUD no deben depender del mecanismo de login."""

    app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@example.com",
        rol="administrador",
        primer_ingreso=False,
    )
    yield
    app.dependency_overrides.pop(require_admin, None)
