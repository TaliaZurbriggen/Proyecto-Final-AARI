"""Reglas de derivación explícita. No usa IA, SMTP ni el padrón de proveedores."""


class ExternalProviderError(Exception):
    def __init__(self, message, *, status=409, code="external_provider_conflict"):
        self.status, self.code = status, code
        super().__init__(message)


def registration_reason(row, *, registered=False):
    if registered:
        return "Los datos de esta elección ya fueron registrados. El historial no se sobrescribe."
    if row["eleccion_estado"] != "decidida":
        return "Primero tenés que elegir el tipo de proveedor."
    if row["proveedor_seleccionado_id"] or row["presupuesto_seleccionado_id"]:
        return "Ya hay un proveedor o presupuesto seleccionado. El cambio corresponde a la reelección."
    if row["tipo_proveedor"] == "propio" and row["estado"] == "Pendiente de datos de proveedor propio":
        return None
    if (row["tipo_proveedor"] == "fidelizado"
            and row["estado"] in {"Pendiente de asignación", "Sin presupuestos recibidos"}
            and row.get("ronda_estado") in {"esperando", "disponibles", "sin_presupuestos", "revision"}
            and (row.get("presupuestos_disponibles", 0) > 0 or row["estado"] == "Sin presupuestos recibidos")):
        return None
    return "La etapa actual del reclamo no permite registrar un proveedor externo."
