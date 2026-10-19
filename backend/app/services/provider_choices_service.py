"""Reglas de etapa y plazos para elegir proveedor."""


class ProviderChoiceNotFound(Exception):
    pass


class ProviderChoiceForbidden(Exception):
    pass


class ProviderChoiceConflict(Exception):
    pass


def valid_stage(row):
    return ((row["tipo_gasto"] == "ordinario" and row["actor_tipo"] == "inquilino"
             and row["estado"] == "Pendiente de respuesta del responsable")
            or (row["tipo_gasto"] == "extraordinario" and row["actor_tipo"] == "propietario"
                and row["estado"] == "Autorizado"))


def can_choose(row, now):
    return row["solicitud_estado"] == "pendiente" and valid_stage(row) and now < row["respuesta_vence_en"]


def ensure_choice_allowed(row, request, now):
    if not can_choose(row, now):
        raise ProviderChoiceConflict("La elección ya fue registrada, venció o cambió la etapa del reclamo.")
    if str(row["solicitud_id"]) != str(request.solicitud_id) or row["updated_at"] != request.expected_updated_at:
        raise ProviderChoiceConflict("El reclamo cambió. Actualizá la pantalla antes de elegir.")
