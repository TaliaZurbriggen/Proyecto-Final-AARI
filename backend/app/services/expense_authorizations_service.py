"""Errores y reglas puras de autorización; sin llamadas externas."""

from datetime import datetime


class ExpenseAuthorizationNotFound(Exception):
    pass


class ExpenseAuthorizationForbidden(Exception):
    pass


class ExpenseAuthorizationConflict(Exception):
    pass


def can_decide(*, state: str, expense: str, actor: str, deadline: datetime,
               now: datetime) -> bool:
    return (state == "Pendiente de respuesta del responsable"
            and expense == "extraordinario" and actor == "propietario"
            and now < deadline)


def ensure_decision_allowed(row, expected_updated_at, now):
    if not can_decide(state=row["estado"], expense=row["tipo_gasto"],
                      actor=row["actor_tipo"], deadline=row["respuesta_vence_en"], now=now):
        raise ExpenseAuthorizationConflict("El reclamo ya no admite esta decisión o venció el plazo.")
    if row["updated_at"] != expected_updated_at:
        raise ExpenseAuthorizationConflict("El reclamo cambió. Actualizá la pantalla antes de decidir.")
