"""Orquestación contractual. No interpreta firmas ni cláusulas."""

import hashlib
import logging
import re
from datetime import datetime
from io import BytesIO
from math import ceil
from uuid import uuid4
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from app.schemas.contratos import ContractResponse, ContractsPage, DocumentDownload
from app.services.contract_errors import ContractError
from app.services.contract_storage import DOWNLOAD_TTL

MAX_PDF_SIZE = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


def today_ar():
    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()


def validate_pdf(content: bytes, filename: str, content_type: str | None):
    if not content or len(content) > MAX_PDF_SIZE:
        raise ContractError("El PDF debe pesar entre 1 byte y 10 MB.", field="archivo")
    if not filename.lower().endswith(".pdf") or content_type not in {"application/pdf", "application/octet-stream"}:
        raise ContractError("Seleccioná un archivo PDF.", field="archivo")
    if not content.startswith(b"%PDF-"):
        raise ContractError("El archivo no es un PDF válido.", field="archivo")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ContractError("El PDF está protegido con contraseña. Cargá una copia sin contraseña.", field="archivo")
        if not len(reader.pages):
            raise ValueError("PDF sin páginas")
    except ContractError:
        raise
    except Exception as error:
        raise ContractError("El PDF está dañado o no puede leerse. Probá con otra copia.", field="archivo") from error
    name = re.sub(r"[\x00-\x1f\x7f]", "", filename.replace("\\", "/").split("/")[-1]).strip()
    return (name[:176] + ".pdf") if len(name) > 180 else name


class ContractsService:
    def __init__(self, repository, storage, today=today_ar):
        self.repository, self.storage, self.today = repository, storage, today

    @staticmethod
    def _admin(user):
        if user.rol != "administrador" or user.primer_ingreso:
            raise ContractError("Solo la inmobiliaria puede administrar contratos.", status=403)

    def _response(self, record):
        data = dict(record)
        start, end = data["fecha_inicio"], data["fecha_fin"]
        # Pydantic normaliza fechas de SQLite y PostgreSQL.
        from app.db.contratos import as_date
        if data["estado"] == "borrador":
            label = "Borrador"
        elif data["estado"] == "finalizado":
            label = "Finalizado"
        elif self.today() < as_date(start):
            label = "Próximo a iniciar"
        elif self.today() > as_date(end):
            label = "Vencido"
        else:
            label = "Vigente"
        return ContractResponse.model_validate({**data, "vigencia": label})

    def list(self, user, **filters):
        records, total = self.repository.list(user, **filters)
        size, page = filters.get("page_size", 10), filters.get("page", 1)
        return ContractsPage(items=[self._response(r) for r in records],
                             page=page, page_size=size, total=total,
                             total_pages=ceil(total / size))

    def get(self, contract_id, user):
        return self._response(self.repository.get(contract_id, user))

    def create(self, payload, user):
        self._admin(user)
        return self.get(self.repository.create(payload, user.id), user)

    def update(self, contract_id, payload, user):
        self._admin(user)
        self.repository.update(contract_id, payload, user.id)
        return self.get(contract_id, user)

    def upload(self, contract_id, user, *, content, filename, content_type, signed, revision):
        self._admin(user)
        current = self.repository.get(contract_id, user)
        if current["revision"] != revision:
            raise ContractError("El contrato cambió. Recargá la pantalla.", code="contract_stale", status=409)
        if current["estado"] == "finalizado" or (current["estado"] == "firmado" and not signed):
            raise ContractError("Este contrato no admite ese cambio de documento.", status=409)
        clean_name = validate_pdf(content, filename, content_type)
        document_id = str(uuid4())
        path = f"{contract_id}/{document_id}.pdf"
        document = {"id": document_id, "storage_path": path, "nombre_archivo": clean_name,
                    "tamano": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        # La ruta es única: nunca se sobrescribe una versión anterior.
        try:
            self.storage.upload(path, content)
            self.repository.save_document(contract_id, document, signed, revision, user.id)
        except Exception:
            try:
                # Un fallo de conexión durante COMMIT puede tener resultado incierto.
                # No borrar un documento si existe o si no se puede comprobar su estado.
                if not self.repository.document_exists(document_id):
                    self.storage.delete(path)
            except Exception:
                logger.warning("HU29: verificar carga incompleta %s", document_id)
            raise
        return self.get(contract_id, user)

    def download(self, contract_id, document_id, user):
        record = self.repository.get(contract_id, user)
        document = next((d for d in record["documentos"] if str(d["id"]) == str(document_id)), None)
        if document is None:
            raise ContractError("No encontramos el documento solicitado.", status=404)
        return DocumentDownload(url=self.storage.signed_url(document["storage_path"]), expires_in=DOWNLOAD_TTL)

    def end(self, contract_id, payload, user):
        self._admin(user)
        self.repository.end(contract_id, payload, user.id, self.today())
        return self.get(contract_id, user)
