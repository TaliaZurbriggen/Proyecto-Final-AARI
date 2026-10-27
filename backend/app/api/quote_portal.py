"""Rutas HU19 con identidad desde sesión, no desde parámetros del cliente."""

import os
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.api.auth import require_roles
from app.db.quote_portal import SqlAlchemyQuotePortal
from app.schemas.auth import AuthenticatedUser
from app.schemas.quote_portal import PortalQuoteRequest
from app.services.quote_portal import QuotePortalError

def ensure_enabled():
    if os.getenv('AARI_QUOTE_PORTAL_ENABLED','false').lower() not in {'1','true','yes'}:
        raise HTTPException(503,detail={'code':'quote_portal_disabled','message':'La recepción de presupuestos todavía no está habilitada.'})


router=APIRouter(tags=['presupuestos AARI'], dependencies=[Depends(ensure_enabled)])
provider= require_roles('proveedor')
participant= require_roles('administrador','operador','inquilino','propietario')


def get_quote_portal(): return SqlAlchemyQuotePortal()


def call(response, operation):
    response.headers['Cache-Control']='no-store'
    try: return operation()
    except QuotePortalError as e:
        raise HTTPException(e.status,detail={'code':e.code,'message':str(e)}) from None


@router.get('/proveedor/solicitudes')
def list_requests(response:Response,page:int=Query(1,ge=1,le=2147483647),page_size:int=Query(10,ge=1,le=50),
                  estado:Literal['pendientes','enviadas','todas']=Query('pendientes'),
                  user:AuthenticatedUser=Depends(provider),repo=Depends(get_quote_portal)):
    return call(response,lambda:repo.list_own(user,page,page_size,status=estado))


@router.get('/proveedor/solicitudes/{request_id}')
def get_request(request_id:UUID,response:Response,user:AuthenticatedUser=Depends(provider),repo=Depends(get_quote_portal)):
    return call(response,lambda:repo.get_own(request_id,user))


@router.post('/proveedor/solicitudes/{request_id}/presupuesto')
def submit_quote(request_id:UUID,payload:PortalQuoteRequest,response:Response,
                 user:AuthenticatedUser=Depends(provider),repo=Depends(get_quote_portal)):
    return call(response,lambda:repo.submit(request_id,user,payload))


@router.get('/reclamos/{claim_id}/presupuestos')
def claim_quotes(claim_id:UUID,response:Response,user:AuthenticatedUser=Depends(participant),repo=Depends(get_quote_portal)):
    return call(response,lambda:repo.for_claim(claim_id,user))
