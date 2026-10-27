"""HU19 AARI: publicación y vencimientos locales; entrega por outbox existente."""

import asyncio
import logging
import os
from urllib.parse import urlsplit, urlunsplit


class QuotePortalError(Exception):
    def __init__(self, message, *, status=409, code='quote_conflict'):
        super().__init__(message)
        self.status, self.code = status, code


def portal_link(path):
    base = urlsplit(os.getenv('APP_LOGIN_URL', 'http://localhost:5173/login'))
    if (base.username or base.password or not base.hostname or
        (base.scheme != 'https' and not (base.scheme == 'http' and base.hostname in {'localhost','127.0.0.1','::1'}))):
        raise QuotePortalError('La URL de acceso no está configurada de forma segura.', code='invalid_portal_url')
    return urlunsplit((base.scheme, base.netloc, path, '', ''))


class AariQuoteWorker:
    def __init__(self, repository): self.repository = repository

    def tick(self):
        return self.repository.discover_portal() + self.repository.finalize_due_portal()


def build_aari_quote_worker():
    from app.db.quote_portal import SqlAlchemyQuotePortal
    return AariQuoteWorker(SqlAlchemyQuotePortal())


async def run_aari_quote_worker(worker, stop_event, *, poll_seconds=5):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(worker.tick)
        except Exception:
            logging.getLogger(__name__).error('No se pudo procesar la ronda de presupuestos de AARI.')
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
