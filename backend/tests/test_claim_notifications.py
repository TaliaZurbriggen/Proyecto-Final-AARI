"""Pruebas del correo en segundo plano sin conectarse a SMTP."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.services.claim_notifications import (
    ClaimEmailDeliveryError,
    ClaimNotificationContext,
    ClaimNotificationService,
)


@dataclass
class FakeRepository:
    context: ClaimNotificationContext | None
    results: list[tuple[bool, str | None]] = field(default_factory=list)

    def get_notification_context(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None:
        return self.context

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        sent: bool,
        safe_error: str | None = None,
    ) -> None:
        self.results.append((sent, safe_error))


class FakeSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def send(self, **data) -> None:
        self.calls.append(data)
        if self.fail:
            raise ClaimEmailDeliveryError("SMTP simulado no disponible.")


def notification_context() -> ClaimNotificationContext:
    return ClaimNotificationContext(
        recipient="lucia@example.com",
        claim_number=12,
        message="Recibimos tu reclamo.",
    )


def test_marks_notification_as_sent_after_sender_accepts_it():
    repository = FakeRepository(notification_context())
    sender = FakeSender()

    assert ClaimNotificationService(repository, sender).deliver(uuid4()) is True
    assert repository.results == [(True, None)]
    assert sender.calls[0]["claim_number"] == 12


def test_marks_only_notification_as_failed_when_smtp_rejects_it():
    repository = FakeRepository(notification_context())
    sender = FakeSender(fail=True)

    assert ClaimNotificationService(repository, sender).deliver(uuid4()) is False
    assert repository.results == [(False, "SMTP simulado no disponible.")]
