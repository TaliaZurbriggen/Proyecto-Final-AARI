"""HU14: API y consultas privadas con SQL SQLite aislado; ningún servicio externo."""

from datetime import UTC, datetime
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_current_user
from app.api.configuracion import get_agency_configuration_repository
from app.api.expensas import get_expenses_repository
from app.db.configuracion import SqlAlchemyAgencyConfigurationRepository
from app.db.expensas import SqlAlchemyExpensesRepository
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.expensas import ExpenseFilters, ExpenseNoteRequest, ExpenseReport
from app.services.expense_notifications import agency_email, expense_message, expense_report


@pytest.fixture
def expense_case():
    db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    meta = MetaData()
    props = Table("propiedades", meta, Column("id",String,primary_key=True),
        *(Column(name,String) for name in ("direccion","provincia","localidad","barrio","tipo","numero")), Column("piso",Integer))
    claims = Table("reclamos",meta,Column("id",String,primary_key=True), Column("numero",Integer),
        *(Column(name,String) for name in ("descripcion","estado","tipo_gasto","propiedad_id")),Column("creado_en",DateTime))
    notifications = Table("notificaciones",meta,Column("id",String,primary_key=True),
        *(Column(name,String) for name in ("reclamo_id","destinatario_tipo","destinatario_contacto","canal","estado_envio","ultimo_error")),
        Column("intentos",Integer),Column("enviado_en",DateTime),Column("created_at",DateTime))
    reports = Table("reclamo_derivaciones_expensa",meta,Column("reclamo_id",String,primary_key=True),
        Column("reporte",String),Column("notificacion_id",String),Column("error_configuracion",String))
    users = Table("usuarios",meta,Column("id",String,primary_key=True),Column("email",String),Column("nombre_completo",String),
        Column("rol",String),Column("activo",Boolean),Column("primer_ingreso",Boolean))
    Table("notas_internas",meta,Column("id",String,primary_key=True),Column("reclamo_id",String),Column("usuario_id",String),
        Column("contenido",String),Column("created_at",DateTime,server_default=text("CURRENT_TIMESTAMP")))
    Table("configuracion_sistema",meta,Column("clave",String,primary_key=True),Column("valor",String),Column("descripcion",String),
        Column("updated_at",DateTime,server_default=text("CURRENT_TIMESTAMP")))
    meta.create_all(db)
    admin = AuthenticatedUser(id=uuid4(), email="admin@example.com",rol="administrador",primer_ingreso=False)
    prop_id, claim_id, notification_id = [uuid4() for _ in range(3)]
    now = datetime(2026,10,1,12,tzinfo=UTC)
    prop = {"id":str(prop_id),"direccion":"Unidad de prueba","provincia":"Córdoba","localidad":"Localidad sintética",
            "barrio":None,"tipo":"casa","piso":None,"numero":None}
    report = ExpenseReport(reclamo_id=claim_id,numero=1,ingresado_en=now,clasificado_en=now,propiedad=prop,
        inquilino={"nombre":"Contacto sintético","email":"tenant@example.com"},
        descripcion="Falla en instalación común.",urgencia="media",fundamento="Corresponde evaluar expensa.",origen="agente",confianza=0.95)
    with db.begin() as conn:
        conn.execute(users.insert(),{"id":str(admin.id),"email":admin.email,"nombre_completo":"Cuenta sintética",
                                    "rol":"administrador","activo":True,"primer_ingreso":False})
        conn.execute(props.insert(),prop)
        conn.execute(claims.insert(),{"id":str(claim_id),"numero":1,"descripcion":report.descripcion,"estado":"Derivado a inmobiliaria (expensa)",
            "tipo_gasto":"expensa","propiedad_id":str(prop_id),"creado_en":now})
        conn.execute(notifications.insert(),{"id":str(notification_id),"reclamo_id":str(claim_id),"destinatario_tipo":"inmobiliaria",
            "destinatario_contacto":"agency@example.com","canal":"email","estado_envio":"enviado","intentos":1,"enviado_en":now,"created_at":now})
        conn.execute(reports.insert(),{"reclamo_id":str(claim_id),"reporte":report.model_dump_json(),"notificacion_id":str(notification_id)})
    sessions = sessionmaker(bind=db)
    repository, config = SqlAlchemyExpensesRepository(sessions), SqlAlchemyAgencyConfigurationRepository(sessions)
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_expenses_repository] = lambda: repository
    app.dependency_overrides[get_agency_configuration_repository] = lambda: config
    with TestClient(app) as client:
        yield {"client":client,"db":db,"repo":repository,"config":config,"admin":admin,
               "id":claim_id,"property":prop_id,"report":report,"notification":notification_id,
               "claims":claims}
    for dependency in (get_current_user,get_expenses_repository,get_agency_configuration_repository):
        app.dependency_overrides.pop(dependency,None)
    db.dispose()


def test_list_and_snapshot_do_not_expose_notes(expense_case):
    c = expense_case
    data = c["client"].get('/expensas')
    assert data.status_code == 200 and data.json()['total'] == 1
    assert data.headers['X-Total-Count'] == '1'
    assert 'reporte' not in data.json()['items'][0] and 'notas' not in data.json()['items'][0]
    detail = c["client"].get(f'/expensas/{c["id"]}').json()
    assert detail['reporte']['inquilino']['email'] == 'tenant@example.com'
    assert detail['envios'][0]['estado'] == 'enviado' and detail['notas'] == []


def test_private_note_is_append_only_and_server_assigns_identity(expense_case):
    c=expense_case
    path=f'/expensas/{c["id"]}/notas'
    response=c['client'].post(path,json={"contenido":"  Revisar con administración.  "})
    assert response.status_code==201
    note=response.json()
    assert note['usuario_id']==str(c['admin'].id) and note['creado_en']
    assert note['contenido']=='Revisar con administración.'
    assert len(c['client'].get(f'/expensas/{c["id"]}').json()['notas'])==1
    assert c['client'].post(path,json={"contenido":"Nota","usuario_id":str(uuid4())}).status_code==422
    assert c['client'].delete(path+'/'+note['id']).status_code==404


@pytest.mark.parametrize('role',["inquilino","propietario","proveedor"])
def test_unauthorized_roles_cannot_read_or_write_any_private_endpoint(expense_case,role):
    c=expense_case
    app.dependency_overrides[get_current_user]=lambda: c['admin'].model_copy(update={"rol":role})
    for url in ['/expensas',f'/expensas/{c["id"]}','/configuracion/correo-inmobiliaria']:
        assert c['client'].get(url).status_code==403
    assert c['client'].post(f'/expensas/{c["id"]}/notas',json={"contenido":"Nota"}).status_code==403
    assert c['client'].put('/configuracion/correo-inmobiliaria',json={"email":"agency@example.com"}).status_code==403


def test_operator_reads_and_adds_notes_but_does_not_configure(expense_case):
    c=expense_case
    with c['db'].begin() as conn:
        conn.execute(text("UPDATE usuarios SET rol='operador'"))
    app.dependency_overrides[get_current_user]=lambda: c['admin'].model_copy(update={"rol":"operador"})
    assert c['client'].get('/expensas').status_code==200
    assert c['client'].post(f'/expensas/{c["id"]}/notas',json={"contenido":"Nota operativa"}).status_code==201
    assert c['client'].get('/configuracion/correo-inmobiliaria').status_code==403


def test_first_login_and_mid_request_deactivation_prevent_writes(expense_case):
    c=expense_case
    app.dependency_overrides[get_current_user]=lambda: c['admin'].model_copy(update={"primer_ingreso":True})
    assert c['client'].get('/expensas').status_code==403
    app.dependency_overrides[get_current_user]=lambda: c['admin']
    with c['db'].begin() as conn:
        conn.execute(text('UPDATE usuarios SET activo=false'))
    assert c['client'].post(f'/expensas/{c["id"]}/notas',json={"contenido":"Nota"}).status_code==403


def test_email_setting_validation_and_snapshot_are_independent(expense_case):
    c=expense_case
    assert c['client'].get('/configuracion/correo-inmobiliaria').json()['configurado'] is False
    assert c['client'].put('/configuracion/correo-inmobiliaria',json={"email":"invalid"}).status_code==422
    response=c['client'].put('/configuracion/correo-inmobiliaria',json={"email":"Other@EXAMPLE.COM"})
    assert response.status_code==200 and response.json()['email']=='other@example.com'
    assert c['client'].get('/configuracion/correo-inmobiliaria').json()['configurado'] is True
    assert c['client'].get(f'/expensas/{c["id"]}').json()['envios'][0]['destinatario']=='agency@example.com'


@pytest.mark.parametrize('content',['','   ','x'*1001])
def test_invalid_notes_are_rejected(expense_case,content):
    c=expense_case
    assert c['client'].post(f'/expensas/{c["id"]}/notas',json={"contenido":content}).status_code==422


def test_bad_filters_not_found_and_missing_session(expense_case):
    c=expense_case
    for params in ({"page":0},{"situacion":"invalid"},{"fecha_desde":"2026-10-02","fecha_hasta":"2026-10-01"},
                   {"fecha_hasta":"9999-12-31"},{"propiedad_id":"' OR 1=1"}):
        assert c['client'].get('/expensas',params=params).status_code==422
    assert c['client'].get(f'/expensas/{uuid4()}').status_code==404
    app.dependency_overrides.pop(get_current_user)
    assert c['client'].get('/expensas').status_code==401


def test_pagination_and_empty_property_filters(expense_case):
    c=expense_case
    now=datetime(2026,10,1,12,tzinfo=UTC)
    with c['db'].begin() as conn:
        conn.execute(c['claims'].insert(),[{'id':str(uuid4()),'numero':n,'descripcion':'Caso sintético',
            'estado':'Derivado a inmobiliaria (expensa)','tipo_gasto':'expensa','propiedad_id':str(c['property']),'creado_en':now}
            for n in range(2,26)])
    first=c['client'].get('/expensas').json()
    second=c['client'].get('/expensas?page=2').json()
    assert first['total']==25 and len(first['items'])==20 and len(second['items'])==5
    assert [x['numero'] for x in first['items']]==list(range(25,5,-1))
    assert c['client'].get('/expensas',params={'propiedad_id':str(uuid4())}).json()['total']==0
    assert c['client'].get('/expensas?situacion=historicos').json()['total']==24


def test_status_counts_include_failures_without_fake_success(expense_case):
    c=expense_case
    with c['db'].begin() as conn:
        conn.execute(text("UPDATE notificaciones SET estado_envio='fallido', intentos=3, enviado_en=NULL, ultimo_error='No se pudo entregar.'"))
        conn.execute(text("UPDATE reclamos SET estado='Pendiente de respuesta del responsable'"))
    data=c['client'].get('/expensas').json()
    assert data['total']==0 and data['fallidos']==1
    failed=c['client'].get('/expensas?situacion=fallidos').json()
    assert failed['items'][0]['entrega_estado']=='fallido' and failed['items'][0]['intentos']==3


def test_templates_normalize_contact_without_leaking_internal_fields(expense_case,monkeypatch):
    monkeypatch.setenv('APP_LOGIN_URL','https://aari.example.com/login')
    message=expense_message(expense_case['report'])
    assert 'no autoriza gastos' in message and 'aari.example.com/expensas/' in message
    assert 'DNI' not in message and 'notas' not in message and '95%' in message
    assert agency_email(' invalid ')==None and agency_email('Agency@EXAMPLE.COM')=='agency@example.com'
    assert ExpenseFilters().situacion=='derivados'
    assert ExpenseNoteRequest(contenido=' nota ').contenido=='nota'


def test_mail_link_does_not_include_userinfo_query_or_fragment(expense_case,monkeypatch):
    monkeypatch.setenv('APP_LOGIN_URL','https://test-user@aari.example.com/login?private=excluded#fragment')
    message=expense_message(expense_case['report'])
    assert 'https://aari.example.com/expensas/' in message
    assert 'test-user' not in message and 'private=excluded' not in message and '#fragment' not in message


@pytest.mark.parametrize('origin', ['operador', 'administrador'])
def test_report_factory_preserves_human_origin_without_agent_confidence(expense_case, origin):
    """Contrato HU14 para el helper manual de HU13, sin importar su rama pendiente."""
    original = expense_case['report']
    context = {
        'id': original.reclamo_id,
        'numero': original.numero,
        'creado_en': original.ingresado_en,
        'clasificado_en': original.clasificado_en,
        'inquilino_nombre': original.inquilino.nombre,
        'inquilino_email': original.inquilino.email,
        'descripcion': original.descripcion,
        'urgencia': original.urgencia,
    }
    # Incluso si el resultado anterior conservaba confianza, no atribuirla
    # a una decisión humana ni enviarla en el reporte.
    result = SimpleNamespace(fundamento='Revisión humana de una instalación común.', confianza=0.95)
    report = expense_report(context, result, original.propiedad, origin=origin)
    assert report.origen == origin and report.confianza is None
    assert report.reclamo_id == original.reclamo_id
    assert report.fundamento == result.fundamento
    message = expense_message(report)
    assert f'Origen: {origin}' in message
    assert 'No corresponde (decisión humana)' in message and '95%' not in message
