"""La identidad, la etapa y los destinatarios nunca vienen del formulario."""

from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictBool


class CoordinationCancellationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    eleccion_id: UUID
    expected_updated_at: AwareDatetime
    confirmar: StrictBool
