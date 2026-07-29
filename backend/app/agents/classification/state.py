"""Estado compartido por los nodos del flujo de clasificación."""

from typing import Literal

from typing_extensions import NotRequired, TypedDict


TipoGasto = Literal["ordinario", "extraordinario", "expensa"]
EstadoClasificacion = Literal["pendiente_modelo", "clasificado", "escalado"]
MotivoEscalado = Literal["respuesta_modelo_invalida"]


class ClassificationState(TypedDict):
    """Datos que acompañan a un reclamo durante su clasificación.

    Los campos de salida son opcionales porque el reclamo ingresa al grafo sin
    clasificar. AARI-107 completa los datos devueltos por Gemini y AARI-108
    decidirá si corresponde escalar el caso según su confianza.
    """

    descripcion: str
    urgencia: Literal["baja", "media", "alta"]
    reclamo_id: NotRequired[str]
    tipo_gasto: NotRequired[TipoGasto | None]
    confianza: NotRequired[float | None]
    fundamento: NotRequired[str | None]
    debe_escalar: NotRequired[bool]
    motivo_escalado: NotRequired[MotivoEscalado | None]
    estado_clasificacion: NotRequired[EstadoClasificacion]