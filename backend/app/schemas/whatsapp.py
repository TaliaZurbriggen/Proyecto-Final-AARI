"""Eventos de transporte: no representan presupuestos ni decisiones de negocio."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class WhatsAppInboundEvent:
    waba_id: str
    phone_number_id: str
    event_key: str
    external_id: str
    kind: str
    event_type: str
    participant: str = field(repr=False)
    occurred_at: datetime
    data: dict = field(repr=False)
    state: str = "pendiente"


@dataclass(frozen=True)
class WhatsAppIngestionResult:
    inserted: int
    duplicated: int


@dataclass(frozen=True)
class WhatsAppSendReceipt:
    message_id: str
    # La aceptación HTTP de Meta no acredita entrega al destinatario.
    outcome: str = "accepted"
