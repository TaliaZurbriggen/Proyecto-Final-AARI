"""Gestión por inmobiliaria y consulta por participantes autenticados."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.auth import require_roles
from app.db.contratos import SqlAlchemyContractsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.contratos import (
    ContractCreate, ContractEnd, ContractResponse, ContractsPage,
    ContractUpdate, DocumentDownload,
)
from app.services.contract_errors import ContractError
from app.services.contract_storage import SupabaseContractStorage
from app.services.contracts_service import ContractsService, MAX_PDF_SIZE

router = APIRouter(prefix="/contratos", tags=["contratos"])
contract_user = require_roles("administrador", "inquilino", "propietario")


def get_contracts_service():
    return ContractsService(SqlAlchemyContractsRepository(), SupabaseContractStorage())


@router.get("", response_model=ContractsPage)
def list_contracts(
    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
    inquilino_id: UUID | None = None, propiedad_id: UUID | None = None,
    search: str = Query("", max_length=200),
    user: AuthenticatedUser = Depends(contract_user),
    service: ContractsService = Depends(get_contracts_service),
):
    return service.list(user, page=page, page_size=page_size,
                        inquilino_id=inquilino_id, propiedad_id=propiedad_id, search=search)


@router.post("", response_model=ContractResponse, status_code=201)
def create_contract(payload: ContractCreate, user: AuthenticatedUser = Depends(contract_user),
                    service: ContractsService = Depends(get_contracts_service)):
    return service.create(payload, user)


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(contract_id: UUID, user: AuthenticatedUser = Depends(contract_user),
                 service: ContractsService = Depends(get_contracts_service)):
    return service.get(contract_id, user)


@router.patch("/{contract_id}", response_model=ContractResponse)
def update_contract(contract_id: UUID, payload: ContractUpdate,
                    user: AuthenticatedUser = Depends(contract_user),
                    service: ContractsService = Depends(get_contracts_service)):
    return service.update(contract_id, payload, user)


@router.post("/{contract_id}/documentos", response_model=ContractResponse)
async def upload_document(
    contract_id: UUID, archivo: UploadFile = File(...),
    firmado: bool = Form(False), revision: int = Form(..., ge=1),
    user: AuthenticatedUser = Depends(contract_user),
    service: ContractsService = Depends(get_contracts_service),
):
    try:
        service._admin(user)
        if archivo.size is not None and archivo.size > MAX_PDF_SIZE:
            raise ContractError("El PDF no puede superar los 10 MB.", field="archivo")
        content = await archivo.read(MAX_PDF_SIZE + 1)
        if len(content) > MAX_PDF_SIZE:
            raise ContractError("El PDF no puede superar los 10 MB.", field="archivo")
        return await run_in_threadpool(
            service.upload, contract_id, user, content=content,
            filename=archivo.filename or "", content_type=archivo.content_type,
            signed=firmado, revision=revision,
        )
    finally:
        await archivo.close()


@router.post("/{contract_id}/documentos/{document_id}/descarga", response_model=DocumentDownload)
def download_document(contract_id: UUID, document_id: UUID, response: Response,
                      user: AuthenticatedUser = Depends(contract_user),
                      service: ContractsService = Depends(get_contracts_service)):
    response.headers["Cache-Control"] = "no-store"
    return service.download(contract_id, document_id, user)


@router.post("/{contract_id}/finalizar", response_model=ContractResponse)
def end_contract(contract_id: UUID, payload: ContractEnd,
                 user: AuthenticatedUser = Depends(contract_user),
                 service: ContractsService = Depends(get_contracts_service)):
    return service.end(contract_id, payload, user)
