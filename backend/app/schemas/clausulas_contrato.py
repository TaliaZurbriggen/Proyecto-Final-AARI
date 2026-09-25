"""Contratos validados para la extracción y revisión de cláusulas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ClauseCategory = Literal[
    "reparacion", "mantenimiento", "danio", "servicio", "expensa",
    "aviso", "acceso", "devolucion", "otro",
]
ClauseResponsible = Literal[
    "inquilino", "propietario", "administracion", "condicional", "no_especificado",
]
ClauseUsage = Literal["operativa", "contexto", "excluir"]
ReviewState = Literal["pendiente", "confirmada", "editada", "descartada"]
AnalysisState = Literal["pendiente", "procesando", "completado", "incompleto", "fallido"]


class ClauseEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pagina: int = Field(ge=1)
    texto: str = Field(min_length=1, max_length=8000)

    @field_validator("texto", mode="before")
    @classmethod
    def trim_evidence(cls, value):
        return value.strip() if isinstance(value, str) else value


class ExtractedClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero: str | None = Field(default=None, max_length=80)
    titulo: str | None = Field(default=None, max_length=200)
    evidencias: list[ClauseEvidence] = Field(min_length=1, max_length=20)
    paginas: list[int] = Field(default_factory=list)
    texto_original: str = Field(default="", max_length=8000)
    resumen: str = Field(min_length=1, max_length=1200)
    categoria: ClauseCategory
    responsable: ClauseResponsible
    uso_clasificador: ClauseUsage
    condiciones: str | None = Field(default=None, max_length=1600)
    referencias: list[str] = Field(default_factory=list, max_length=20)
    confianza: float = Field(ge=0, le=1)

    @field_validator("paginas")
    @classmethod
    def valid_pages(cls, value: list[int]) -> list[int]:
        pages = sorted(set(value))
        if not pages or pages[0] < 1:
            raise ValueError("Las páginas deben ser números positivos.")
        return pages

    @field_validator("numero", "titulo", "texto_original", "resumen", "condiciones", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("referencias")
    @classmethod
    def clean_references(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def derive_combined_evidence(self):
        if not self.evidencias:
            if self.paginas and self.texto_original:
                return self
            raise ValueError("La cláusula debe conservar evidencia verificable.")
        evidence_pages = sorted({item.pagina for item in self.evidencias})
        combined = "\n\n".join(item.texto for item in self.evidencias)
        self.paginas = evidence_pages
        self.texto_original = combined
        return self


class RejectedClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(ge=1)
    propuesta: ExtractedClause
    motivo: str = Field(min_length=1, max_length=1000)
    evidencias_invalidas: list[ClauseEvidence] = Field(default_factory=list)


class ExtractedClauseBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clausulas: list[ExtractedClause] = Field(default_factory=list, max_length=120)


class ContractClauseResponse(ExtractedClause):
    evidencias: list[ClauseEvidence] = Field(default_factory=list)
    uso_clasificador: ClauseUsage = "operativa"
    id: UUID
    ordinal: int
    estado_revision: ReviewState
    revision: int
    revisado_por: UUID | None = None
    revisado_en: datetime | None = None


class ContractAnalysisResponse(BaseModel):
    id: UUID
    contrato_id: UUID
    documento_id: UUID
    estado: AnalysisState
    completo: bool
    paginas_total: int | None = None
    lectura_paginas: list[dict[str, object]] = Field(default_factory=list)
    intentos: int
    ultimo_error: str | None = None
    created_at: datetime
    updated_at: datetime
    clausulas: list[ContractClauseResponse] = Field(default_factory=list)
    propuestas_rechazadas: list[RejectedClause] = Field(default_factory=list)


class ClauseReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accion: Literal["confirmar", "editar", "descartar"]
    revision: int = Field(ge=1)
    resumen: str | None = Field(default=None, min_length=1, max_length=1200)
    categoria: ClauseCategory | None = None
    responsable: ClauseResponsible | None = None
    uso_clasificador: ClauseUsage | None = None
    condiciones: str | None = Field(default=None, max_length=1600)

    @model_validator(mode="after")
    def validate_edit(self):
        editable = (
            self.resumen, self.categoria, self.responsable,
            self.uso_clasificador, self.condiciones,
        )
        if self.accion == "editar" and all(value is None for value in editable):
            raise ValueError("Indicá al menos un cambio para editar la cláusula.")
        if self.accion != "editar" and any(value is not None for value in editable):
            raise ValueError("Los cambios de contenido solo corresponden a la acción editar.")
        return self
