"""Bandeja privada de entrada. El ACK sólo se devuelve después del commit."""

from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import Column, DateTime, MetaData, Table, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.schemas.whatsapp import WhatsAppInboundEvent, WhatsAppIngestionResult


INBOX = Table(
    "whatsapp_eventos_entrada", MetaData(),
    Column("id", UUID), Column("waba_id", Text), Column("telefono_id", Text),
    Column("clave_evento", Text), Column("mensaje_externo_id", Text),
    Column("tipo_evento", Text), Column("subtipo", Text), Column("participante", Text),
    Column("ocurrido_en", DateTime(timezone=True)), Column("datos", JSONB), Column("estado", Text),
    schema="public",
)


class SqlAlchemyWhatsAppInbox:
    def __init__(self, session_factory=None):
        if session_factory is None:
            from app.db.database import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory

    def save_events(self, events: Sequence[WhatsAppInboundEvent]) -> WhatsAppIngestionResult:
        if not events:
            return WhatsAppIngestionResult(0, 0)
        # Un orden estable evita interbloqueos si llegan IDs en distinto orden.
        # Un único INSERT evita un viaje de red por cada evento del lote.
        rows = [{
            "id": uuid4(), "waba_id": event.waba_id, "telefono_id": event.phone_number_id,
            "clave_evento": event.event_key, "mensaje_externo_id": event.external_id,
            "tipo_evento": event.kind, "subtipo": event.event_type,
            "participante": event.participant, "ocurrido_en": event.occurred_at,
            "datos": event.data, "estado": event.state,
        } for event in sorted(events, key=lambda value: (value.waba_id, value.phone_number_id, value.event_key))]
        statement = insert(INBOX).values(rows).on_conflict_do_nothing(
            index_elements=[INBOX.c.waba_id, INBOX.c.telefono_id, INBOX.c.clave_evento],
        ).returning(INBOX.c.id)
        with self.session_factory.begin() as session:
            inserted = len(session.execute(statement).scalars().all())
        return WhatsAppIngestionResult(inserted, len(events) - inserted)
