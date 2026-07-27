"""Estado compartido por los nodos del flujo de clasificación."""

from typing import Literal

from typing_extensions import NotRequired, TypedDict


TipoGasto = Literal["ordinario", "extraordinario", "expensa"]
EstadoClasificacion = Literal["pendiente_modelo", "clasificado", "escalado"]


class ClassificationState(TypedDict):
    """Datos que acompañan a un reclamo durante su clasificación.

    Los campos de salida son opcionales porque el reclamo ingresa al grafo sin
    clasificar. Se completarán cuando se integre el modelo en AARI-107 y la
    lógica de escalado en AARI-108.
    """

    descripcion: str
    urgencia: Literal["baja", "media", "alta"]
    reclamo_id: NotRequired[str]
    tipo_gasto: NotRequired[TipoGasto | None]
    confianza: NotRequired[float | None]
    fundamento: NotRequired[str | None]
    debe_escalar: NotRequired[bool]
    motivo_escalado: NotRequired[str | None]
    estado_clasificacion: NotRequired[EstadoClasificacion]