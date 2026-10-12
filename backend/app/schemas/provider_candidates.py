"""HU15: consulta privada y comando explícito de búsqueda, sin asignación final."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.proveedores import EspecialidadResponse, ProveedorResponse
from app.schemas.reclamos import ClaimPropertyContext

SearchOutcome = Literal[
    "candidatos_encontrados", "sin_candidatos", "especialidad_pendiente", "ubicacion_incompleta",
]
AlertOutcome = Literal["no_aplica", "encolado", "sin_destinatario"]


class CandidateSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_updated_at: datetime
    especialidad_id: UUID | None = None

    @field_validator("expected_updated_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("La versión del reclamo debe incluir zona horaria.")
        return value


class CandidateSearchAudit(BaseModel):
    id: UUID
    buscado_en: datetime
    origen: Literal["administrador", "operador", "agente"]
    usuario_id: UUID | None
    especialidad_id: UUID | None
    especialidad_anterior_id: UUID | None
    provincia: str | None
    localidad: str | None
    barrio: str | None
    resultado: SearchOutcome
    candidato_ids: list[UUID]
    aviso_operador: AlertOutcome


class CandidateClaimItem(BaseModel):
    id: UUID
    numero: int
    descripcion: str
    estado: str
    creado_en: datetime
    updated_at: datetime
    propiedad: ClaimPropertyContext
    especialidad: EspecialidadResponse | None
    ultimo_resultado: SearchOutcome | None = None
    aviso_operador: AlertOutcome | None = None


class CandidateClaimsPage(BaseModel):
    items: list[CandidateClaimItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CandidateProvidersPage(CandidateClaimItem):
    tipo_gasto: Literal["ordinario", "extraordinario", "expensa"] | None
    tarea_agente: Literal["pendiente", "procesando", "completada", "revision", "cancelada"] | None = None
    motivo_agente: str | None = None
    puede_buscar: bool
    resultado: SearchOutcome
    candidatos: list[ProveedorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    historial_busquedas: list[CandidateSearchAudit]
    # Auditoría paginada, independiente del listado de proveedores.
    historial_total: int


class CandidateSearchExecution(BaseModel):
    busqueda_id: UUID
    resultado: SearchOutcome
    candidato_ids: list[UUID]
    aviso_operador: AlertOutcome
    repetida: bool = False
