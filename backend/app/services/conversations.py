"""Reglas compartidas del canal HU33. Sin LLM, SMTP ni decisiones económicas."""

import os


def conversations_enabled():
    return os.getenv('AARI_CONVERSATIONS_ENABLED', 'false').strip().lower() in {'1', 'true', 'yes'}


class ConversationError(Exception):
    def __init__(self, message, *, status=409, code='conversation_conflict'):
        super().__init__(message)
        self.status, self.code = status, code


EVENT_MESSAGES = {
    'publicada': 'El agente publicó esta solicitud de presupuesto. Todavía no confirma una contratación ni una visita.',
    'presupuesto_registrado': 'El proveedor presentó su presupuesto mediante el formulario. El responsable debe revisarlo; todavía no confirma contratación.',
    'vencida': 'Finalizó la recepción de presupuestos de esta ronda. El chat no amplía el plazo para presentar uno.',
    'cancelada': 'Este intento fue cancelado. Se conserva el historial y no se permiten nuevas acciones.',
    'revision': 'Esta ronda requiere revisión de la inmobiliaria.',
}


def budget_write_reason(context, now, *, current):
    if context['ronda_estado'] == 'cancelada':
        return 'Este intento fue cancelado. El historial queda en sólo lectura.'
    if context['proveedor_seleccionado_id'] is not None or context['presupuesto_seleccionado_id'] is not None:
        return 'La etapa de presupuesto finalizó. La coordinación de la visita es una etapa separada.'
    if not current:
        return 'La solicitud cambió o ya no está vigente. El historial queda en sólo lectura.'
    if not context['presupuesto_id'] and (context['cerrada_en'] is not None or now >= context['vence_en']):
        return 'La solicitud venció sin presupuesto. El historial queda en sólo lectura.'
    return None
