"""Errores públicos del circuito contractual, sin datos del documento."""


from functools import wraps

from sqlalchemy.exc import IntegrityError


class ContractError(Exception):
    def __init__(self, message: str, *, code: str = "contract_error",
                 status: int = 422, field: str | None = None) -> None:
        super().__init__(message)
        self.code, self.status, self.field = code, status, field


class ContractHistoryError(ContractError):
    def __init__(self) -> None:
        super().__init__(
            "No se puede eliminar el registro porque tiene contratos asociados. "
            "Su historial debe conservarse.",
            code="contract_history", status=409,
        )


def translate_contract_fk(error) -> None:
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", "") or ""
    if constraint in {
        "contratos_inquilino_id_fkey", "contratos_propiedad_id_fkey",
        "contratos_propietario_id_fkey",
    }:
        raise ContractHistoryError from error


def preserve_contract_history(method):
    """Traduce la FK restrictiva sin agregar consultas a módulos preexistentes."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except IntegrityError as error:
            translate_contract_fk(error)
            raise
    return wrapped
