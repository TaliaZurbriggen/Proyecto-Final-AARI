"""Consultas de reclamos propias del inquilino autenticado."""

from typing import Protocol
from uuid import UUID

from app.schemas.reclamos import TenantClaimDetail, TenantClaimListItem


class TenantClaimNotFoundError(Exception):
    """El reclamo no existe o no pertenece al inquilino autenticado."""


class TenantClaimsQueryRepository(Protocol):
    def list_for_tenant(
        self, *, user_id: UUID, profile_id: UUID
    ) -> list[TenantClaimListItem]: ...

    def get_for_tenant(
        self, *, claim_id: UUID, user_id: UUID, profile_id: UUID
    ) -> TenantClaimDetail | None: ...


class TenantClaimsQueryService:
    """Impide consultar reclamos ajenos aun si se conoce su UUID."""

    def __init__(self, repository: TenantClaimsQueryRepository) -> None:
        self.repository = repository

    def list(
        self, *, user_id: UUID, profile_id: UUID | None
    ) -> list[TenantClaimListItem]:
        if profile_id is None:
            return []
        return self.repository.list_for_tenant(
            user_id=user_id,
            profile_id=profile_id,
        )

    def get(
        self, *, claim_id: UUID, user_id: UUID, profile_id: UUID | None
    ) -> TenantClaimDetail:
        if profile_id is None:
            raise TenantClaimNotFoundError
        claim = self.repository.get_for_tenant(
            claim_id=claim_id,
            user_id=user_id,
            profile_id=profile_id,
        )
        if claim is None:
            raise TenantClaimNotFoundError
        return claim
