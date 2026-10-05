"""Orquestación durable de extracción, revisión y reintentos."""

import asyncio
import logging
import os
from typing import Callable

from pydantic import ValidationError

from app.schemas.clausulas_contrato import (
    ClauseReviewRequest,
)
from app.schemas.analisis_asistido import AssistedAnalysisResponse as ContractAnalysisResponse
from app.services.contract_clause_assisted import (
    DEFAULT_MODEL,
    PROMPT_VERSION,
    EXTRACTOR_VERSION,
    get_assisted_model,
    interpret,
    literal_clauses,
)
from app.services.contract_errors import ContractError
from app.services.contract_text_extraction import (
    ContractTextError,
    extract_contract_text,
)


LOGGER = logging.getLogger(__name__)


class ContractClauseService:
    def __init__(self, repository, storage, *, model_factory: Callable = get_assisted_model, ocr=None):
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

    def request(self, contract_id, document_id, user, *, mode="ia"):
        self._admin(user)
        if mode not in {"ia", "literal"}:
            raise ContractError("Modo de extracción inválido.", status=422)
        self.repository.document_for_analysis(contract_id, document_id)
        analysis_id = self.repository.request_analysis(
            contract_id, document_id, user.id,
            extractor=EXTRACTOR_VERSION,
            prompt=PROMPT_VERSION if mode == "ia" else "sin-interpretacion",
            model=os.getenv("CONTRACT_CLAUSE_MODEL", DEFAULT_MODEL) if mode == "ia" else "local",
            mode=mode,
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
            if (job.mode == "ia" and job.prompt_version is not None
                    and job.prompt_version != PROMPT_VERSION):
                self._fail(job, "El intento pertenece a una versión anterior. Solicitá un nuevo análisis.")
                return
            pdf = self.storage.download(job.storage_path)
            extracted = extract_contract_text(pdf, self.ocr)
            clauses, source_rejected, incidents = [], [], []
            origins = []
            if job.mode == "ia":
                model = (self.model_factory(job.model_name) if self.model_factory is get_assisted_model
                         else self.model_factory())
                clauses, source_rejected, incidents = interpret(extracted, model)
                origins = ["ia"] * len(clauses)
            literals = literal_clauses(extracted)
            covered = {(clause.texto_original, tuple(clause.paginas)) for clause in clauses}
            for clause in literals:
                if (clause.texto_original, tuple(clause.paginas)) not in covered:
                    clauses.append(clause)
                    origins.append("literal")
            unreadable = [str(page.page) for page in extracted.pages if not page.readable]
            if unreadable:
                incidents.append("Páginas sin lectura confiable: " + ", ".join(unreadable) + ".")
            page_summary = [
                {"pagina": page.page, "metodo": page.method, "legible": page.readable}
                for page in extracted.pages
            ]
            self.repository.complete(
                job.id, pages=page_summary, clauses=clauses, rejected=[],
                complete=extracted.complete, incidents=incidents,
                extractor_version=EXTRACTOR_VERSION, source_rejected=source_rejected,
                origins=origins, execution_id=job.execution_id,
            )
        except ContractTextError as error:
            self._fail(job, str(error))
        except (ValidationError, ValueError, TypeError):
            self._fail(
                job,
                "El modelo devolvió una respuesta que no pudo validarse.",
            )
        except RuntimeError as error:
            self._fail(job, "El análisis no está disponible. Revisá la configuración o usá la extracción sin IA.")
        except Exception:
            # No registrar excepciones del proveedor: pueden contener prompt o credenciales.
            LOGGER.warning("Falló el análisis contractual %s; contenido omitido.", job.id)
            self._fail(
                job,
                "No se pudo completar el análisis. Podés reintentarlo o extraer sin IA.",
            )

    def _fail(self, job, message):
        self.repository.fail(job.id, job.attempt_number, message, execution_id=job.execution_id)


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
