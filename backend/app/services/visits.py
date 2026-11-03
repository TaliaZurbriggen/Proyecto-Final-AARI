"""Reglas de horarios y worker opt-in. No envía correo ni consume Gemini."""
import asyncio
from datetime import timedelta
import logging
import os
from zoneinfo import ZoneInfo

ARGENTINA = ZoneInfo('America/Argentina/Buenos_Aires')
WAITING = {'esperando_confirmacion', 'negociando'}


class VisitError(Exception):
    def __init__(self, message, *, status=409, code='visit_conflict'):
        super().__init__(message)
        self.status, self.code = status, code


def visits_enabled():
    return os.getenv('AARI_VISITS_ENABLED', 'false').strip().lower() in {'1', 'true', 'yes'}


def validate_options(options, now):
    days = set()
    for option in options:
        start, end = option.desde.astimezone(ARGENTINA), option.hasta.astimezone(ARGENTINA)
        if start <= now or start.date() != end.date() or end <= start:
            raise VisitError('Las opciones deben ser futuras, con inicio y fin dentro del mismo día de Argentina.', status=422)
        if start.second or start.microsecond or end.second or end.microsecond:
            raise VisitError('Ingresá horarios con precisión de minutos.', status=422)
        if start.date() in days:
            raise VisitError('Elegí al menos tres fechas distintas, sin repetir días.', status=422)
        days.add(start.date())
    if not 3 <= len(days) <= 10:
        raise VisitError('Ingresá entre tres y diez fechas distintas.', status=422)


def valid_time(value, now):
    if value <= now or value.second or value.microsecond:
        raise VisitError('Elegí una fecha futura con precisión de minutos.', status=422)


def reminder_due(confirmed_at, visit_at, now, hours):
    due = visit_at - timedelta(hours=hours)
    # No emitir recordatorios retroactivos ni después de la visita.
    return confirmed_at <= due <= now < visit_at


async def run_visit_worker(repo, stop_event, *, poll_seconds=30):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(repo.tick, limit=20)
        except Exception:
            logging.getLogger(__name__).error('No se pudo actualizar la coordinación de visitas.')
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
