"""Plantillas puras para avisar al responsable de un reclamo clasificado."""

from dataclasses import dataclass

from app.agents.classification.state import ActorResponsable, TipoGasto


@dataclass(frozen=True)
class ResponsibleNotificationData:
    claim_number: int
    actor: ActorResponsable
    actor_name: str
    expense_type: TipoGasto
    description: str
    property_label: str


def initial_subject(data: ResponsibleNotificationData) -> str:
    return f"AARI - Acción requerida en reclamo #{data.claim_number:06d}"


def initial_message(data: ResponsibleNotificationData) -> str:
    introductions = {
        "inquilino": (
            "El reclamo fue clasificado como un gasto ordinario a tu cargo. "
            "Necesitamos que indiques cómo querés continuar."
        ),
        "propietario": (
            "El reclamo fue clasificado como un gasto extraordinario. "
            "Necesitamos tu autorización para continuar con la gestión."
        ),
        "inmobiliaria": (
            "El reclamo fue clasificado como expensa. "
            "La inmobiliaria debe evaluar cómo continuar."
        ),
    }
    return "\n".join(
        [
            f"Hola {data.actor_name},",
            "",
            introductions[data.actor],
            f"Reclamo: AARI #{data.claim_number:06d}",
            f"Unidad: {data.property_label}",
            f"Descripción: {data.description}",
            "",
            "El reclamo quedó pendiente de la respuesta del responsable.",
        ]
    )


def reminder_subject(data: ResponsibleNotificationData) -> str:
    return f"AARI - Recordatorio del reclamo #{data.claim_number:06d}"


def reminder_message(data: ResponsibleNotificationData) -> str:
    return "\n".join(
        [
            f"Hola {data.actor_name},",
            "",
            f"El reclamo AARI #{data.claim_number:06d} continúa esperando tu respuesta.",
            f"Unidad: {data.property_label}",
            "Si no recibimos una respuesta dentro de las próximas 24 horas, "
            "el caso se marcará como vencido para intervención operativa.",
        ]
    )


def overdue_operator_subject(claim_number: int) -> str:
    return f"AARI - Respuesta vencida en reclamo #{claim_number:06d}"


def overdue_operator_message(
    *, claim_number: int, actor: ActorResponsable, property_label: str
) -> str:
    return "\n".join(
        [
            f"El reclamo AARI #{claim_number:06d} agotó el plazo de respuesta.",
            f"Responsable esperado: {actor}.",
            f"Unidad: {property_label}",
            "El estado cambió a Pendiente de respuesta - vencido y requiere intervención.",
        ]
    )
