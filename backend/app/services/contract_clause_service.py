"""Orquestación durable de extracción, revisión y reintentos."""

import asyncio
import logging
import os
from typing import Callable

from pydantic import ValidationError

from app.schemas.clausulas_contrato import (
    ClauseReviewRequest,
    ContractAnalysisResponse,
)
from app.services.contract_clause_llm import (
    DEFAULT_MODEL,
    EXTRACTOR_VERSION,
    PROMPT_VERSION,
    build_clause_prompt,
    get_clause_model,
    parse_batch,
)
from app.services.contract_clause_evidence import validate_and_anchor_evidence
from app.services.contract_errors import ContractError
from app.services.contract_text_extraction import (
    ContractTextError,
    extract_contract_text,
    minimize_personal_data,
)


LOGGER = logging.getLogger(__name__)


class ContractClauseService:
    def __init__(self, repository, storage, *, model_factory: Callable = get_clause_model, ocr=None):
        self.repository = repository
        self.storage = storage
        self.model_factory = model_factory
        self.ocr = ocr

    @staticmethod
    def _admin(user):
        if user.rol != "administrador" or user.primer_ingreso:
            raise ContractError("Solo la inmobiliaria puede revisar cláusulas.", status=403)

    @staticmethod
    def _response(record):
        return ContractAnalysisResponse.model_validate(record) if record else None

    def request(self, contract_id, document_id, user):
        self._admin(user)
        self.repository.document_for_analysis(contract_id, document_id)
        analysis_id = self.repository.request_analysis(
            contract_id, document_id, user.id,
            extractor=EXTRACTOR_VERSION,
            prompt=PROMPT_VERSION,
            model=os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL),
        )
        return self._response(self.repository.get(contract_id, analysis_id))

    def get_for_document(self, contract_id, document_id, user):
        self._admin(user)
        return self._response(self.repository.get_for_document(contract_id, document_id))

    def review(self, contract_id, clause_id, payload: ClauseReviewRequest, user):
        self._admin(user)
        return self._response(self.repository.review(contract_id, clause_id, payload, user.id))

    def process_due(self, *, limit=3):
        jobs = self.repository.claim_due(limit=limit)
        for job in jobs:
            self._process(job)
        return len(jobs)

    def _process(self, job):
        try:
            pdf = self.storage.download(job.storage_path)
            extracted = extract_contract_text(pdf, self.ocr)
            minimized = minimize_personal_data(extracted.model_text)
            result = parse_batch(self.model_factory().invoke(build_clause_prompt(minimized)))
            pages = {page.page: page.text for page in extracted.pages}
            clauses, rejected, incidents = validate_and_anchor_evidence(result, pages)
            unreadable = [str(page.page) for page in extracted.pages if not page.readable]
            if unreadable:
                incidents.append("Páginas sin lectura confiable: " + ", ".join(unreadable) + ".")
            page_summary = [
                {"pagina": page.page, "metodo": page.method, "legible": page.readable}
                for page in extracted.pages
            ]
            self.repository.complete(
                job.id, pages=page_summary, clauses=clauses, rejected=rejected,
                complete=extracted.complete, incidents=incidents,
            )
        except ContractTextError as error:
            self.repository.fail(job.id, job.attempt_number, str(error))
        except (ValidationError, ValueError, TypeError):
            self.repository.fail(
                job.id, job.attempt_number,
                "El modelo devolvió una respuesta que no pudo validarse.",
            )
        except RuntimeError as error:
            self.repository.fail(job.id, job.attempt_number, str(error))
        except Exception:
            LOGGER.exception("Falló el análisis contractual %s sin registrar contenido privado.", job.id)
            self.repository.fail(
                job.id, job.attempt_number,
                "No se pudo completar el análisis. Intentaremos nuevamente.",
            )


async def run_contract_analysis_worker(
    service: ContractClauseService,
    stop_event: asyncio.Event,
    *,
    poll_interval_seconds: float = 5,
):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(service.process_due)
        except Exception:
            LOGGER.exception("No se pudo consultar la bandeja de análisis contractuales.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
        except TimeoutError:
            continue
