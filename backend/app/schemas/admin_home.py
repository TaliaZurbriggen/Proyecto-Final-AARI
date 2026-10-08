"""Resumen operativo privado del Home administrativo (HU31)."""

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class EntityCount(BaseModel):
    total: int = Field(ge=0)


class ActiveEntityCount(EntityCount):
    activos: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_active_count(self):
        if self.activos > self.total:
            raise ValueError("Los activos no pueden superar el total.")
        return self


class ClaimsSummary(BaseModel):
    activos: int = Field(ge=0)
    pendientes_clasificacion: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_pending_count(self):
        if self.pendientes_clasificacion > self.activos:
            raise ValueError("Los pendientes están incluidos en los activos.")
        return self


class AdminHomeSummary(BaseModel):
    consultado_en: AwareDatetime
    propietarios: EntityCount
    propiedades: EntityCount
    inquilinos: EntityCount
    proveedores: ActiveEntityCount
    operadores: ActiveEntityCount
    reclamos: ClaimsSummary
