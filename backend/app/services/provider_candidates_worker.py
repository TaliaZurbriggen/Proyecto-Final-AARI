"""Ejecución durable de HU15: un trabajo por vez, sin decisiones comerciales."""

import asyncio
import logging
import os
from threading import Event, Thread

from app.agents.provider_candidates import build_provider_candidates_graph

logger = logging.getLogger(__name__)


class ProviderCandidatesWorker:
    def __init__(self, repository, *, resolver=None, external_enabled=None, heartbeat_seconds=30):
        self.repository = repository
        self.resolver = resolver
        self.external_enabled = external_enabled if external_enabled is not None else (
            os.getenv("PROVIDER_SPECIALTY_EXTERNAL_ENABLED", "false").lower() in {"1", "true", "yes"}
        )
        self.heartbeat_seconds = heartbeat_seconds

    def process_one(self):
        self.repository.discover()
        job = self.repository.reserve_one()
        if job is None:
            return False
        stop, lost = Event(), Event()

        def heartbeat():
            while not stop.wait(self.heartbeat_seconds):
                try:
                    if not self.repository.renew(job):
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if not self.repository.renew(job):
                return False
            def persist(state):
                if lost.is_set():
                    return None
                return self.repository.finish(job, state)
            graph = build_provider_candidates_graph(
                persist, resolver=self.resolver, external_enabled=self.external_enabled,
            )
            graph.invoke({"descripcion": job["descripcion"], "tipo_id": job["tipo_id"], "catalogo": job["catalogo"]})
            return True
        finally:
            stop.set()
            thread.join(timeout=2)


async def run_provider_candidates_worker(worker, stop_event):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(worker.process_one)
        except Exception:
            # Sin exception/traceback: no exponer SQL, descripciones o claves.
            logger.warning("HU15: búsqueda automática interrumpida; revisar el registro de tareas.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15)
        except TimeoutError:
            pass
