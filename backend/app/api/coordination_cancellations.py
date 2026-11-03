"""Cancelación HU24 con confirmación explícita y cuenta responsable vigente."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from app.api.auth import require_roles
from app.api.quote_portal import call
from app.db.coordination_cancellations import SqlAlchemyCoordinationCancellations
from app.schemas.auth import AuthenticatedUser
from app.schemas.coordination_cancellations import CoordinationCancellationRequest
from app.services.coordination_cancellations import cancellations_enabled


def ensure_enabled():
    if not cancellations_enabled():
        raise HTTPException(503,detail={'code':'cancellation_disabled','message':'La cancelación todavía no está habilitada.'})


router=APIRouter(tags=['cancelación de coordinación'],dependencies=[Depends(ensure_enabled)])
responsible=require_roles('inquilino','propietario')


def get_cancellations():
    return SqlAlchemyCoordinationCancellations()


@router.get('/reclamos/{claim_id}/cancelacion-coordinacion')
def cancellation_detail(claim_id: UUID,response: Response,user: AuthenticatedUser=Depends(responsible),repo=Depends(get_cancellations)):
    return call(response,lambda:repo.get(claim_id,user))


@router.post('/reclamos/{claim_id}/cancelacion-coordinacion')
def cancel_coordination(claim_id: UUID,payload: CoordinationCancellationRequest,response: Response,
                        user: AuthenticatedUser=Depends(responsible),repo=Depends(get_cancellations)):
    return call(response,lambda:repo.cancel(claim_id,user,payload))
