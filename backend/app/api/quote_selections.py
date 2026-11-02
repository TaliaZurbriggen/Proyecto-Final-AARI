"""HU20: consulta del responsable y confirmación explícita autenticada."""

from uuid import UUID
from fastapi import APIRouter, Depends, Response

from app.api.auth import require_roles
from app.api.quote_portal import ensure_enabled, call
from app.db.quote_selections import SqlAlchemyQuoteSelections
from app.schemas.auth import AuthenticatedUser
from app.schemas.quote_selections import QuoteSelectionRequest


router = APIRouter(tags=['selección de presupuestos'], dependencies=[Depends(ensure_enabled)])
reader = require_roles('administrador', 'operador', 'inquilino', 'propietario')
responsible = require_roles('inquilino', 'propietario')


def get_quote_selections():
    return SqlAlchemyQuoteSelections()


@router.get('/reclamos/{claim_id}/seleccion-presupuesto')
def get_selection(claim_id: UUID, response: Response, user: AuthenticatedUser = Depends(reader),
                  repo=Depends(get_quote_selections)):
    return call(response, lambda: repo.get(claim_id, user))


@router.post('/reclamos/{claim_id}/seleccion-presupuesto')
def select_quote(claim_id: UUID, payload: QuoteSelectionRequest, response: Response,
                 user: AuthenticatedUser = Depends(responsible), repo=Depends(get_quote_selections)):
    return call(response, lambda: repo.choose(claim_id, user, payload))
