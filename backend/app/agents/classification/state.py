"""Estado compartido por los nodos del flujo de clasificaci?n."""

from typing import Literal

from typing_extensions import NotRequired, TypedDict


TipoGasto = Literal["ordinario", "extraordinario", "expensa"]
EstadoClasificacion = Literal["pendiente_modelo", "clasificado", "escalado"]
MotivoEscalado = Literal[
    "respuesta_modelo_invalida",
    "riesgo_seguridad",
    "multiples_rubros",
    "causa_no_identificable",
    "confianza_insuficiente",
]


class ClassificationState(TypedDict):
    """Datos que acompanan a un reclamo durante su clasificaci?n."""

    descripcion: str
    urgencia: Literal["baja", "media", "alta"]
    reclamo_id: NotRequired[str]
    rubro_declarado: NotRequired[str | None]
    clausulas_contrato: NotRequired[list[dict[str, object]]]
    tipo_gasto: NotRequired[TipoGasto | None]
    confianza: NotRequired[float | None]
    fundamento: NotRequired[str | None]
    debe_escalar: NotRequired[bool]
    motivo_escalado: NotRequired[MotivoEscalado | None]
    estado_clasificacion: NotRequired[EstadoClasificacion]
