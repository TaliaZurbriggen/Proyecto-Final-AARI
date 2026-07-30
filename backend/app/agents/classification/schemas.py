"""Contratos estructurados entre Gemini y el grafo de clasificaci?n."""

from pydantic import BaseModel, Field, model_validator

from .state import MotivoEscalado, TipoGasto


class ModelClassification(BaseModel):
    """Resultado validado que el modelo debe devolver para un reclamo."""

    tipo_gasto: TipoGasto | None
    confianza: float = Field(ge=0, le=1)
    fundamento: str = Field(min_length=1)
    debe_escalar: bool
    motivo_escalado: MotivoEscalado | None

    @model_validator(mode="after")
    def validate_escalation_contract(self) -> "ModelClassification":
        """Evita aceptar una salida contradictoria del modelo."""

        if self.debe_escalar:
            if self.tipo_gasto is not None or self.motivo_escalado is None:
                raise ValueError(
                    "Un resultado escalado requiere tipo_gasto nulo y motivo_escalado."
                )
        elif self.tipo_gasto is None or self.motivo_escalado is not None:
            raise ValueError(
                "Un resultado clasificado requiere tipo_gasto y no admite motivo_escalado."
            )
        return self
