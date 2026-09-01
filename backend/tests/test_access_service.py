from uuid import UUID

import pytest

from app.services.access_service import (
    AccessAlreadyActivatedError,
    AccessInvitationService,
    AccessNotFoundError,
    WelcomeEmailDeliveryError,
)


USER_ID = UUID("00000000-0000-0000-0000-000000000068")
PERSON_ID = UUID("00000000-0000-0000-0000-000000000069")


class FakeAccessRepository:
    def __init__(self, context=None):
        self.context = context
        self.results = []

    def mark_delivery_result(self, user_id, *, sent, safe_error=None):
        self.results.append((user_id, sent, safe_error))

    def get_delivery_context(self, *, entity, entity_id):
        assert entity in {"propietario", "inquilino"}
        assert entity_id == PERSON_ID
        return self.context


class FakeSender:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    def send(self, **message):
        self.messages.append(message)
        if self.error:
            raise self.error


def context(**changes):
    return {
        "usuario_id": USER_ID,
        "primer_ingreso": True,
        "nombre_completo": "Ana Martínez",
        "dni": "30123456",
        "email": "ana@example.com",
        "estado": "pendiente",
        **changes,
    }


def test_delivery_marks_email_as_sent():
    repository = FakeAccessRepository()
    sender = FakeSender()

    sent = AccessInvitationService(repository, sender).deliver(
        user_id=USER_ID,
        recipient="ana@example.com",
        person_name="Ana Martínez",
        temporary_password="30123456",
    )

    assert sent is True
    assert repository.results == [(USER_ID, True, None)]
    assert sender.messages[0]["temporary_password"] == "30123456"


def test_delivery_failure_is_persisted_without_aborting_account_creation():
    repository = FakeAccessRepository()
    sender = FakeSender(
        WelcomeEmailDeliveryError("El servicio de correo no está configurado.")
    )

    sent = AccessInvitationService(repository, sender).deliver(
        user_id=USER_ID,
        recipient="ana@example.com",
        person_name="Ana Martínez",
        temporary_password="30123456",
    )

    assert sent is False
    assert repository.results == [
        (USER_ID, False, "El servicio de correo no está configurado.")
    ]


def test_retry_uses_current_domain_credentials():
    repository = FakeAccessRepository(context())
    sender = FakeSender()

    sent = AccessInvitationService(repository, sender).retry(
        entity="propietario",
        entity_id=PERSON_ID,
    )

    assert sent is True
    assert sender.messages == [
        {
            "recipient": "ana@example.com",
            "person_name": "Ana Martínez",
            "temporary_password": "30123456",
        }
    ]


def test_retry_rejects_already_activated_or_missing_accounts():
    activated = AccessInvitationService(
        FakeAccessRepository(context(primer_ingreso=False)), FakeSender()
    )
    missing = AccessInvitationService(FakeAccessRepository(), FakeSender())

    with pytest.raises(AccessAlreadyActivatedError):
        activated.retry(entity="inquilino", entity_id=PERSON_ID)
    with pytest.raises(AccessNotFoundError):
        missing.retry(entity="inquilino", entity_id=PERSON_ID)
