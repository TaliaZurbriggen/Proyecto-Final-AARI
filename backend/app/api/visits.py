"""HU23: acciones acotadas, identidades del servidor y respuesta sin caché."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_roles
from app.db.visits import SqlAlchemyVisits
from app.schemas.auth import AuthenticatedUser
from app.schemas.visits import AvailabilityRequest, VisitAction, VisitConfirmationRequest, VisitProposalRequest
from app.services.visits import VisitError, visits_enabled


def ensure_enabled():
    if not visits_enabled():
        raise HTTPException(503,detail={'code':'visits_disabled','message':'La coordinación de visitas todavía no está habilitada.'},headers={'Cache-Control':'no-store'})


router=APIRouter(prefix='/reclamos',tags=['visitas'],dependencies=[Depends(ensure_enabled)])
participant=require_roles('inquilino','proveedor','propietario','administrador','operador')


def get_visits(): return SqlAlchemyVisits()


def call(response, operation):
    response.headers['Cache-Control']='no-store'
    try: return operation()
    except VisitError as error:
        raise HTTPException(error.status,detail={'code':error.code,'message':str(error)},headers={'Cache-Control':'no-store'}) from None
    except SQLAlchemyError:
        raise HTTPException(503,detail={'code':'visits_unavailable','message':'No pudimos consultar la coordinación. Intentá nuevamente.'},headers={'Cache-Control':'no-store'}) from None


@router.get('/visitas/propias')
def own(response:Response,page:int=Query(1,ge=1,le=2147483647),page_size:int=Query(20,ge=1,le=50),
        user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.list_own(user,page=page,page_size=page_size))


@router.get('/{claim_id}/visita')
def detail(claim_id: UUID,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.get(claim_id,user))


@router.post('/{claim_id}/visita/disponibilidad')
def availability(claim_id:UUID,payload:AvailabilityRequest,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.act(claim_id,user,'disponibilidad',payload))


@router.post('/{claim_id}/visita/sin-coincidencia')
def no_match(claim_id:UUID,payload:VisitAction,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.act(claim_id,user,'sin-coincidencia',payload))


@router.post('/{claim_id}/visita/proponer')
def propose(claim_id:UUID,payload:VisitProposalRequest,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.act(claim_id,user,'proponer',payload))


@router.post('/{claim_id}/visita/confirmar')
def confirm(claim_id:UUID,payload:VisitConfirmationRequest,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_visits)):
    return call(response,lambda:repo.act(claim_id,user,'confirmar',payload))
