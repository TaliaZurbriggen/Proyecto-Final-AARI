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
    accept_results: bool = True
    results: list[tuple[int, bool, str | None]] = field(default_factory=list)

    def claim_notification(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None:
        return self.context

    def claim_due_notifications(self, *, limit: int) -> list[ClaimNotificationContext]:
        return [self.context] if self.context else []

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        attempt_number: int,
        sent: bool,
        safe_error: str | None = None,
    ) -> bool:
        self.results.append((attempt_number, sent, safe_error))
        return self.accept_results


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
        id=uuid4(),
        recipient="lucia@example.com",
        claim_number=12,
        channel="email",
        subject="AARI - Reclamo #000012 actualizado",
        message="Recibimos tu reclamo.",
        attempt_number=1,
    )


def test_marks_notification_as_sent_after_sender_accepts_it():
    repository = FakeRepository(notification_context())
    sender = FakeSender()

    assert ClaimNotificationService(repository, sender).deliver(uuid4()) is True
    assert repository.results == [(1, True, None)]
    assert sender.calls[0]["claim_number"] == 12
    assert sender.calls[0]["subject"].endswith("actualizado")


def test_marks_only_notification_as_failed_when_smtp_rejects_it():
    repository = FakeRepository(notification_context())
    sender = FakeSender(fail=True)

    assert ClaimNotificationService(repository, sender).deliver(uuid4()) is False
    assert repository.results == [(1, False, "SMTP simulado no disponible.")]


def test_uses_the_configured_sender_for_whatsapp_without_real_network_calls():
    context = notification_context()
    context = ClaimNotificationContext(
        **{**context.__dict__, "channel": "whatsapp"}
    )
    repository = FakeRepository(context)
    email_sender = FakeSender()
    whatsapp_sender = FakeSender()

    service = ClaimNotificationService(repository, email_sender, whatsapp_sender)

    assert service.deliver(context.id) is True
    assert email_sender.calls == []
    assert whatsapp_sender.calls[0]["recipient"] == "lucia@example.com"


def test_processes_a_due_batch_and_marks_each_result():
    repository = FakeRepository(notification_context())
    sender = FakeSender()

    assert ClaimNotificationService(repository, sender).deliver_due(limit=5) == 1
    assert repository.results == [(1, True, None)]


def test_does_not_confirm_delivery_when_the_claimed_attempt_expired():
    repository = FakeRepository(notification_context(), accept_results=False)
    sender = FakeSender()

    assert ClaimNotificationService(repository, sender).deliver(uuid4()) is False
    assert repository.results == [(1, True, None)]
