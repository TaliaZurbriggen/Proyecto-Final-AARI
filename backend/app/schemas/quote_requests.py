"""Datos internos HU19. No son parámetros de una ruta pública."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class QuoteReservation:
    id: UUID
    claim_id: UUID
    token: UUID
    recipient: str = field(repr=False)
    parameters: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class QuotePreparation:
    round_id: UUID | None
    count: int
    repeated: bool = False
    reason: str | None = None
