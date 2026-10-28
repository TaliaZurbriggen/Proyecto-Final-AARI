"""Worker local de negocio: ningún envío, descarga o llamada a un LLM."""

import asyncio
import logging


class QuoteResponsesWorker:
    def __init__(self, repository):
        self.repository = repository

    def tick(self):
        processed = self.repository.process_pending(limit=100)
        return processed + self.repository.finalize_due(limit=20)


def build_quote_responses_worker():
    from app.db.quote_responses import SqlAlchemyQuoteResponses
    return QuoteResponsesWorker(SqlAlchemyQuoteResponses())


async def run_quote_responses_worker(worker, stop_event, *, poll_seconds=5):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(worker.tick)
        except Exception:
            logging.getLogger(__name__).error("No se pudo procesar la respuesta de presupuesto.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
