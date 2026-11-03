"""Reglas HU24 compartidas por consulta y confirmación."""

import os


def cancellations_enabled():
    return os.getenv('AARI_CANCELLATIONS_ENABLED', 'false').lower() in {'1', 'true', 'yes'}


def cancellation_reason(row, *, authorized, visit_scheduled):
    if visit_scheduled or row['estado'] == 'Visita programada':
        return 'La visita ya está programada. Esta etapa no admite cancelar y reelegir.'
    if not authorized:
        return 'La autorización o el responsable cambió. Consultá a la inmobiliaria.'
    if (row['solicitud_estado'] != 'decidida' or row['tipo_proveedor'] != 'fidelizado'
            or row['estado'] not in {'Pendiente de asignación', 'Proveedor seleccionado'}):
        return 'Esta etapa no admite cancelar y reelegir proveedor.'
    return None
