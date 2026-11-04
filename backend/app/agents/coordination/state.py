"""Contrato versionado entre HU21 y los módulos que confirman decisiones."""

from datetime import datetime
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Stage = Literal[
    "esperando_autorizacion", "esperando_eleccion_proveedor",
    "esperando_presupuestos", "esperando_seleccion_presupuesto",
    "esperando_datos_proveedor", "esperando_confirmacion_visita", "negociando_visita",
    "esperando_disponibilidad", "visita_programada", "derivado_externo",
    "rechazado", "expirada", "intervencion_manual", "finalizado",
]
TERMINAL_STAGES = {"visita_programada", "derivado_externo", "rechazado", "finalizado"}
EXPIRABLE_STAGES = {"esperando_eleccion_proveedor", "esperando_seleccion_presupuesto"}


class DomainContext(BaseModel):
    """Hechos leídos del dominio; jamás una decisión propuesta por el cliente."""

    model_config = ConfigDict(extra="forbid")
    reclamo_id: UUID
    estado: str
    tipo_gasto: Literal["ordinario", "extraordinario", "expensa"]
    actor_responsable: Literal["inquilino", "propietario", "inmobiliaria"]
    propiedad_id: UUID
    inquilino_id: UUID
    propietario_id: UUID
    proveedor_id: UUID | None = None
    presupuesto_id: UUID | None = None
    monto: str | None = None
    fecha_visita: datetime | None = None
    cancelacion_id: UUID | None = None
    vencimiento_especifico: datetime | None = None
    eleccion_id: UUID | None = None
    ronda_id: UUID | None = None
    estado_ronda: str | None = None
    seleccion_id: UUID | None = None
    coordinacion_visita_id: UUID | None = None
    etapa_visita: str | None = None
    version_visita: int | None = Field(default=None, ge=0)


class CoordinationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    reclamo_id: UUID
    intento_id: UUID
    version: int = Field(ge=0)
    etapa: Stage
    dominio: DomainContext
    eventos_recientes: list[str] = Field(default_factory=list, max_length=20)


class ResumeRequest(BaseModel):
    """Retomar no equivale a autorizar, cancelar ni seleccionar un proveedor."""

    model_config = ConfigDict(extra="forbid")
    evento_id: UUID
    intento_id: UUID | None = None
    version_esperada: int = Field(ge=0)


class CoordinationResponse(BaseModel):
    contexto: CoordinationSnapshot
    ultima_actividad: datetime
    duplicado: bool = False
    requiere_sincronizacion: bool = False
    estado_reclamo_actual: str | None = None


class CoordinationState(TypedDict):
    dominio: dict
    contexto: dict
    evento_id: str


def stage_for(domain: DomainContext) -> Stage:
    state = domain.estado
    if domain.tipo_gasto == "expensa":
        return "finalizado"  # HU14 conserva el circuito y su condición de entrega.
    if state == "Visita programada":
        return "visita_programada"
    if state == "Derivado a proveedor externo":
        return "derivado_externo"
    if state == "Rechazado por propietario":
        return "rechazado"
    if state in {"Resuelto", "Resuelto (sin confirmación)"}:
        return "finalizado"
    if state == "Sesión expirada":
        return "expirada"
    if state in {
        "Escalado", "Clasificación pendiente", "Pendiente de respuesta - vencido",
        "Pendiente de autorización - vencido", "Sin presupuestos recibidos",
    }:
        return "intervencion_manual"
    if state == "Pendiente de respuesta del responsable":
        return ("esperando_autorizacion" if domain.tipo_gasto == "extraordinario"
                else "esperando_eleccion_proveedor")
    if state in {"Clasificado", "Autorizado"}:
        return "esperando_eleccion_proveedor"
    if state == "Pendiente de datos de proveedor propio":
        return "esperando_datos_proveedor"
    if state == "Pendiente de asignación":
        if domain.estado_ronda == "disponibles":
            return "esperando_seleccion_presupuesto"
        if domain.estado_ronda in {"revision", "sin_presupuestos", "cancelada"}:
            return "intervencion_manual"
        return "esperando_presupuestos"
    if state == "Proveedor seleccionado":
        if domain.etapa_visita == "esperando_confirmacion":
            return "esperando_confirmacion_visita"
        if domain.etapa_visita == "negociando":
            return "negociando_visita"
        if domain.etapa_visita in {"sin_acuerdo", "invalidada"}:
            return "intervencion_manual"
        return "esperando_disponibilidad"
    # No inferir una acción ante estados que los módulos todavía no acordaron.
    return "intervencion_manual"
