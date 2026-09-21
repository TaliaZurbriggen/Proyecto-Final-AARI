"""Pruebas de las plantillas de HU12 sin conexiones externas."""

import pytest

from app.services.responsible_actor_notifications import (
    ResponsibleNotificationData,
    initial_message,
    initial_subject,
    overdue_operator_message,
    reminder_message,
)


@pytest.mark.parametrize(
    ("actor", "expense_type", "expected"),
    [
        ("inquilino", "ordinario", "gasto ordinario a tu cargo"),
        ("propietario", "extraordinario", "Necesitamos tu autorización"),
        ("inmobiliaria", "expensa", "clasificado como expensa"),
    ],
)
def test_initial_template_explains_the_expected_action(
    actor: str,
    expense_type: str,
    expected: str,
) -> None:
    data = ResponsibleNotificationData(
        claim_number=27,
        actor=actor,
        actor_name="Responsable de prueba",
        expense_type=expense_type,
        description="La instalación presenta una falla persistente.",
        property_label="Unidad sintética",
    )

    assert initial_subject(data).endswith("#000027")
    assert expected in initial_message(data)
    assert "Unidad sintética" in initial_message(data)


def test_reminder_warns_about_the_additional_24_hour_window() -> None:
    data = ResponsibleNotificationData(
        claim_number=8,
        actor="propietario",
        actor_name="Responsable de prueba",
        expense_type="extraordinario",
        description="La instalación presenta una falla persistente.",
        property_label="Unidad sintética",
    )

    message = reminder_message(data)

    assert "próximas 24 horas" in message
    assert "#000008" in message


def test_overdue_message_identifies_the_actor_and_requires_intervention() -> None:
    message = overdue_operator_message(
        claim_number=3,
        actor="inquilino",
        property_label="Unidad sintética",
    )

    assert "Responsable esperado: inquilino" in message
    assert "requiere intervención" in message
