"""Contrato HU19 para precios confirmados, sin interpretar texto con IA."""

from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortalQuoteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    moneda: Literal['ARS', 'USD']
    tipo_importe: Literal['exacto', 'minimo']
    descripcion: str = Field(min_length=10, max_length=2000)

    @field_validator('monto', mode='before')
    @classmethod
    def explicit_amount(cls, value):
        if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
            raise ValueError('Ingresá un importe decimal explícito, sin símbolos ni separadores de miles.')
        if isinstance(value, str) and not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,2})?', value):
            raise ValueError('Ingresá un importe decimal explícito, sin símbolos ni separadores de miles.')
        return value

    @field_validator('descripcion', mode='before')
    @classmethod
    def clean_description(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                raise ValueError('La descripción contiene caracteres no permitidos.')
        return value
