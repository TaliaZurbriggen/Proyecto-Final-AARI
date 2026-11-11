"""Acciones explícitas de HU23. El cliente no elige participantes ni etapas."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class VisitOption(BaseModel):
    model_config = ConfigDict(extra='forbid')
    desde: AwareDatetime
    hasta: AwareDatetime

    @model_validator(mode='after')
    def valid_range(self):
        if self.hasta <= self.desde:
            raise ValueError('La hora hasta debe ser posterior a la hora desde.')
        return self


class VisitAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    coordinacion_id: UUID
    version_esperada: int = Field(ge=0, strict=True)


class AvailabilityRequest(VisitAction):
    opciones: list[VisitOption] = Field(min_length=3, max_length=10)


class VisitProposalRequest(VisitAction):
    fecha: AwareDatetime


class VisitConfirmationRequest(VisitAction):
    # Horario directo: fecha; negociación: aceptar exactamente propuesta_version.
    fecha: AwareDatetime | None = None
    propuesta_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def one_confirmation(self):
        if (self.fecha is None) == (self.propuesta_version is None):
            raise ValueError('Confirmá una opción o una propuesta concreta.')
        return self


VisitNote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class VisitRescheduleRequest(VisitAction):
    fecha: AwareDatetime
    motivo: VisitNote


class VisitRescheduleDecision(VisitAction):
    propuesta_id: UUID
    decision: Literal['aceptar', 'rechazar', 'retirar']


class VisitAbsenceRequest(VisitAction):
    tipo: Literal['no_realizada', 'contraparte_ausente']
    observaciones: VisitNote
