"""Acceso de administración y consulta propia del inquilino, incluso histórica."""

from typing import Protocol
from uuid import UUID

from app.schemas.auth import AuthenticatedUser
from app.schemas.property_claims import (
    PropertyClaimDetail,
    PropertyClaimsFilters,
    PropertyClaimsPage,
)


class PropertyHistoryForbiddenError(Exception):
    pass


class PropertyHistoryNotFoundError(Exception):
    pass


class PropertyHistoryClaimNotFoundError(Exception):
    pass


class PropertyClaimsRepository(Protocol):
    def list(self, *, property_id: UUID, user_id: UUID | None,
             tenant_id: UUID | None, filters: PropertyClaimsFilters) -> PropertyClaimsPage: ...

    def get(self, *, property_id: UUID, claim_id: UUID,
            user_id: UUID | None, tenant_id: UUID | None) -> PropertyClaimDetail: ...


class PropertyClaimsService:
    def __init__(self, repository: PropertyClaimsRepository):
        self.repository = repository

    @staticmethod
    def _scope(user: AuthenticatedUser) -> dict:
        if user.rol == "administrador" and not user.primer_ingreso:
            return {"user_id": None, "tenant_id": None}
        if user.rol == "inquilino" and user.perfil_id and not user.primer_ingreso:
            return {"user_id": user.id, "tenant_id": user.perfil_id}
        raise PropertyHistoryForbiddenError

    def list(self, *, property_id: UUID, user: AuthenticatedUser,
             filters: PropertyClaimsFilters) -> PropertyClaimsPage:
        return self.repository.list(property_id=property_id, filters=filters, **self._scope(user))

    def get(self, *, property_id: UUID, claim_id: UUID,
            user: AuthenticatedUser) -> PropertyClaimDetail:
        return self.repository.get(property_id=property_id, claim_id=claim_id, **self._scope(user))
