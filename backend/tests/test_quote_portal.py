"""HU19: contrato HTTP y precios explícitos, sin correo ni servicios externos."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.auth import get_current_user
from app.api.quote_portal import get_quote_portal
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.quote_portal import PortalQuoteRequest
from app.services.quote_portal import AariQuoteWorker, QuotePortalError, portal_link


def payload(**changes):
    return {'request_id':str(uuid4()), 'monto':'10000.50', 'moneda':'ARS',
            'tipo_importe':'minimo', 'descripcion':'Reparación de cañería y materiales', **changes}


@pytest.mark.parametrize('kind', ['exacto','minimo'])
def test_price_kind_is_explicit_and_decimal(kind):
    result=PortalQuoteRequest(**payload(tipo_importe=kind))
    assert result.tipo_importe==kind and result.monto==Decimal('10000.50')


@pytest.mark.parametrize('changes', [
    {'monto':'0'}, {'monto':'-1'}, {'monto':'10000.123'}, {'monto':'1e4'},
    {'monto':'NaN'}, {'monto':'Infinity'}, {'monto':'10,000'}, {'monto':'$10000'},
    {'monto':True}, {'monto':10.5}, {'monto':'10000000000'}, {'moneda':'EUR'},
    {'tipo_importe':'aproximado'}, {'descripcion':'   corto  '},
    {'descripcion':'trabajo\x00invalido'}, {'monto':' 10000 '},
])
def test_invalid_prices_are_not_interpreted(changes):
    with pytest.raises(ValidationError): PortalQuoteRequest(**payload(**changes))


def test_kind_required_and_identity_cannot_be_sent_by_client():
    data=payload()
    data.pop('tipo_importe')
    with pytest.raises(ValidationError): PortalQuoteRequest(**data)
    with pytest.raises(ValidationError): PortalQuoteRequest(**payload(proveedor_id=str(uuid4())))


@pytest.mark.parametrize('base', ['http://external.example/login','https://user:secret@example.com/login','file:///login'])
def test_email_link_rejects_unsafe_origins(monkeypatch,base):
    monkeypatch.setenv('APP_LOGIN_URL',base)
    with pytest.raises(QuotePortalError): portal_link('/proveedor')


def test_email_link_only_uses_configured_origin(monkeypatch):
    monkeypatch.setenv('APP_LOGIN_URL','https://aari.example/login?old=1#old')
    assert portal_link('/proveedor/solicitudes/123')=='https://aari.example/proveedor/solicitudes/123'


def test_worker_publishes_and_finalizes_without_network():
    calls=[]
    repo=SimpleNamespace(discover_portal=lambda:calls.append('publish') or 2,
                         finalize_due_portal=lambda:calls.append('expire') or 1)
    assert AariQuoteWorker(repo).tick()==3 and calls==['publish','expire']


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED','true')
    user=AuthenticatedUser(id=uuid4(),email='service@example.com',rol='proveedor',primer_ingreso=False,perfil_id=uuid4())
    app.dependency_overrides[get_current_user]=lambda:user
    calls=[]
    repo=SimpleNamespace(list_own=lambda *args,**kwargs:calls.append((*args,kwargs['status'])) or {'items':[], 'total':0},
                         get_own=lambda *args:{'id':str(args[0])},
                         submit=lambda *args:calls.append(args) or {'estado':'respondida'},
                         for_claim=lambda *args:{'items':[]})
    app.dependency_overrides[get_quote_portal]=lambda:repo
    with TestClient(app) as http: yield http,user,repo,calls
    app.dependency_overrides.pop(get_current_user,None)
    app.dependency_overrides.pop(get_quote_portal,None)


def test_authenticated_provider_submits_kind_and_no_store(client):
    http,user,repo,calls=client
    response=http.post(f'/proveedor/solicitudes/{uuid4()}/presupuesto',json=payload())
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert calls[-1][1] is user and calls[-1][2].tipo_importe=='minimo'


@pytest.mark.parametrize('query',['page=0','page=-1','page=bad','page=2147483648','page_size=51','estado=inexistente'])
def test_pagination_is_validated(client,query):
    http,_,_,calls=client
    assert http.get('/proveedor/solicitudes?'+query).status_code==422 and not calls


@pytest.mark.parametrize('state',[None,'pendientes','enviadas','todas'])
def test_api_filters_and_default_pending_are_forwarded_before_pagination(client,state):
    http,user,_,calls=client
    query='?page=2&page_size=10'+('' if state is None else '&estado='+state)
    result=http.get('/proveedor/solicitudes'+query)
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert calls==[(user,2,10,state or 'pendientes')]


@pytest.mark.parametrize('role',['inquilino','propietario','operador','administrador'])
def test_other_roles_cannot_enter_provider_portal(client,role):
    http,user,_,calls=client
    app.dependency_overrides[get_current_user]=lambda:user.model_copy(update={'rol':role})
    assert http.get('/proveedor/solicitudes').status_code==403 and not calls


def test_provider_cannot_read_other_quotes(client):
    assert client[0].get(f'/reclamos/{uuid4()}/presupuestos').status_code==403


def test_disabled_portal_does_not_query_database(client,monkeypatch):
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED','false')
    assert client[0].get('/proveedor/solicitudes').status_code==503 and not client[3]


def test_not_found_is_controlled(client):
    def fail(*_): raise QuotePortalError('No encontramos esa solicitud.',status=404,code='request_not_found')
    client[2].get_own=fail
    result=client[0].get(f'/proveedor/solicitudes/{uuid4()}')
    assert result.status_code==404 and result.json()['detail']['code']=='request_not_found'
