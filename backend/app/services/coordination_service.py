"""Orquestación de HU21 y worker opcional, sin llamadas externas."""

import asyncio
import logging
from typing import Protocol
from uuid import UUID

import psycopg

from app.agents.coordination.state import CoordinationResponse, ResumeRequest
from app.schemas.auth import AuthenticatedUser


class CoordinationError(Exception):
    def __init__(self, message: str, *, code: str = "coordination_conflict", status: int = 409):
        super().__init__(message)
        self.code, self.status = code, status


class CoordinationRepository(Protocol):
    def get(self, claim_id: UUID, user: AuthenticatedUser) -> CoordinationResponse: ...
    def resume(self, claim_id: UUID, request: ResumeRequest,
               user: AuthenticatedUser) -> CoordinationResponse: ...
    def expire_due(self, *, limit: int = 20) -> int: ...


class CoordinationService:
    def __init__(self, repository: CoordinationRepository):
        self.repository = repository

    def get(self, claim_id, user):
        return self._call(self.repository.get, claim_id, user)

    def resume(self, claim_id, request, user):
        return self._call(self.repository.resume, claim_id, request, user)

    def expire_due(self, *, limit=20):
        return self.repository.expire_due(limit=limit)

    @staticmethod
    def _call(method, *args):
        try:
            return method(*args)
        except psycopg.Error:
            raise CoordinationError(
                "La coordinación no está disponible. Verificá su migración y conexión.",
                code="coordination_unavailable", status=503,
            ) from None


async def run_coordination_worker(service, stop_event, *, poll_interval_seconds=30):
    """Solo materializa vencimientos; SMTP queda en el outbox existente."""
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(service.expire_due)
        except Exception:
            # No imprimir conexiones, contexto, conversaciones ni datos personales.
            logging.getLogger(__name__).error("No se pudo procesar el vencimiento de coordinación.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
        except TimeoutError:
            pass
