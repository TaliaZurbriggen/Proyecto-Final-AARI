"""Búsqueda preliminar: no autoriza gastos ni asigna un proveedor."""

from datetime import UTC
import hashlib
import json

from app.schemas.auth import AuthenticatedUser
from app.schemas.provider_candidates import CandidateSearchRequest
from app.schemas.proveedores import normalize_words


class CandidateClaimNotFoundError(Exception):
    pass


class CandidateSearchConflictError(Exception):
    pass


class CandidateSearchPermissionError(Exception):
    pass


class CandidateSpecialtyNotFoundError(Exception):
    pass


def ensure_search_stage(row):
    # Obtener candidatos no es una decisión comercial. Puede hacerse antes de
    # clasificar el gasto o recibir autorización, sin alterar esas decisiones.
    if row["estado"] in {
        "Resuelto", "Resuelto (sin confirmación)", "Rechazado por propietario",
        "Derivado a proveedor externo", "Sesión expirada",
    }:
        raise CandidateSearchConflictError(
            "El reclamo está cerrado o salió de este circuito. "
            "Podés consultar el resultado, pero no registrar otra búsqueda."
        )


def search_inputs(row, specialty_id):
    location = {name: normalize_words(row[name]) if row[name] else None
                for name in ("provincia", "localidad", "barrio")}
    if specialty_id is None:
        return location, "especialidad_pendiente"
    if not location["provincia"] or not location["localidad"]:
        return location, "ubicacion_incompleta"
    return location, None


def request_fingerprint(request, *, origin, user_id):
    body = {
        "version": request.expected_updated_at.astimezone(UTC).isoformat(),
        "especialidad": str(request.especialidad_id) if request.especialidad_id else None,
        "origen": origin, "usuario": str(user_id) if user_id else None,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class ProviderCandidatesService:
    def __init__(self, repository):
        self.repository = repository

    def search(self, claim_id, request: CandidateSearchRequest, user: AuthenticatedUser):
        if user.rol not in {"administrador", "operador"} or user.primer_ingreso:
            raise CandidateSearchPermissionError
        return self.repository.search(
            claim_id, request, origin=user.rol, user_id=user.id,
        )

    def search_from_coordination(self, claim_id, request: CandidateSearchRequest):
        """Puerto interno para coordinación; no suplantable mediante HTTP."""
        return self.repository.search(claim_id, request, origin="agente", user_id=None)
