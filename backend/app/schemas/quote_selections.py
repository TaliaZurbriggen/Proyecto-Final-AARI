"""Confirmación HU20: sólo referencias, nunca importes o identidad del cliente."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class QuoteSelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    ronda_id: UUID
    expected_updated_at: AwareDatetime
    modalidad: Literal['fidelizado']
    presupuesto_id: UUID
