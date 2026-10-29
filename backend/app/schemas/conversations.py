"""Mensajes explícitos: el cliente nunca decide autor, origen ni etapa."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationMessageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    texto: str = Field(min_length=1, max_length=2000)

    @field_validator('texto', mode='before')
    @classmethod
    def normalize_text(cls, value):
        if isinstance(value, str):
            value = value.replace('\r\n', '\n').replace('\r', '\n').strip()
            if any((ord(c) < 32 and c not in '\n\t') or 0xD800 <= ord(c) <= 0xDFFF for c in value):
                raise ValueError('El mensaje contiene caracteres no permitidos.')
        return value


class ConversationReadRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hasta_numero: int = Field(ge=0, le=9223372036854775807, strict=True)


class ConversationActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
