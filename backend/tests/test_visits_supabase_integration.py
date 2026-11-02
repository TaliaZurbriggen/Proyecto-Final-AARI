"""HU20/HU23: login real y dominio real, sólo filas propias y rollback exterior.

Opt-in autorizado. No se modifica una cuenta/reclamo existente ni se consume la
secuencia pública de reclamos. No se omite get_current_user: se usan cookies JWT
emitidas por /auth/login después de verificar un hash real de PostgreSQL.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import secrets
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.api import auth, conversations, quote_selections, visits
from app.db.database import engine
from app.db.access import SqlAlchemyAccessRepository
from app.db.usuarios import SqlAlchemyUsuariosRepository
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
from app.db.quote_portal import SqlAlchemyQuotePortal
from app.db.quote_selections import SqlAlchemyQuoteSelections
from app.db.visits import SqlAlchemyVisits
from app.db.conversations import SqlAlchemyConversations
from app.schemas.auth import AuthenticatedUser
from app.schemas.reclamos import AgentClassificationResult
from app.schemas.expense_authorizations import ExpenseDecisionRequest
from app.schemas.provider_choices import ProviderChoiceRequest
from app.schemas.quote_portal import PortalQuoteRequest
from app.services.auth_service import AuthService
from scripts.check_visits_postgres import inventory, verify
from tests.test_provider_candidates_supabase_integration import RollbackSession

pytestmark=pytest.mark.skipif(os.getenv('RUN_HU23_SUPABASE_INTEGRATION')!='1',
    reason='Requiere autorización explícita HU23 en Supabase, con rollback.')


@contextmanager
def synthetic_case():
    marker=uuid4().hex
    ids={key:uuid4() for key in ('owner','tenant','provider','property','claim','specialty','coverage')}
    password=secrets.token_urlsafe(30)
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
        tx=c.begin()
        before=inventory(c)
        try:
            c.execute(text("SET LOCAL lock_timeout='5s'"))
            c.execute(text("SET LOCAL statement_timeout='15s'"))
            verify(c)
            users={}
            for role in ('operador','propietario','inquilino','proveedor'):
                uid=uuid4()
                email=f'qa-hu23-{role}-{marker}@example.com'
                c.execute(text("""INSERT INTO usuarios(id,email,password_hash,rol,primer_ingreso,nombre_completo)
                    VALUES (:id,:email,crypt(:password,gen_salt('bf')),CAST(:role AS rol_usuario),false,'Persona Sintetica')"""),
                    {'id':uid,'email':email,'password':password,'role':role})
                profile=ids[{'propietario':'owner','inquilino':'tenant','proveedor':'provider'}[role]] if role!='operador' else None
                users[role]=AuthenticatedUser(id=uid,email=email,rol=role,primer_ingreso=False,perfil_id=profile)
            city='Localidad QA '+marker
            c.execute(text("""INSERT INTO propietarios(id,nombre_completo,dni,email,telefono,usuario_id)
                VALUES (:id,'Titular Sintetico',:dni,:email,'+15555550001',:user)"""),
                {'id':ids['owner'],'dni':str(10_000_000+ids['owner'].int%90_000_000),
                 'email':users['propietario'].email,'user':users['propietario'].id})
            c.execute(text("""INSERT INTO propiedades(id,direccion,provincia,localidad,barrio,tipo,propietario_id)
                VALUES (:id,:address,'Córdoba',:city,'Centro','casa',:owner)"""),
                {'id':ids['property'],'address':'Unidad QA HU23 '+marker,'city':city,'owner':ids['owner']})
            c.execute(text("""INSERT INTO inquilinos(id,nombre_completo,dni,email,telefono,propiedad_id,usuario_id)
                VALUES (:id,'Inquilino Sintetico',:dni,:email,'+15555550002',:property,:user)"""),
                {'id':ids['tenant'],'dni':str(10_000_000+ids['tenant'].int%90_000_000),'email':users['inquilino'].email,
                 'property':ids['property'],'user':users['inquilino'].id})
            c.execute(text("INSERT INTO especialidades(id,nombre) VALUES (:id,:name)"),
                {'id':ids['specialty'],'name':'Servicio QA HU23 '+marker})
            c.execute(text("""INSERT INTO proveedores(id,nombre_razon_social,telefono,email,usuario_id,activo,hora_inicio,hora_fin)
                VALUES (:id,'Proveedor Sintetico',:phone,:email,:user,true,'08:00','18:00')"""),
                {'id':ids['provider'],'phone':'+1555'+str(ids['provider'].int%10**10).zfill(10),
                 'email':users['proveedor'].email,'user':users['proveedor'].id})
            c.execute(text('INSERT INTO proveedor_especialidades(proveedor_id,especialidad_id) VALUES (:p,:s)'),
                {'p':ids['provider'],'s':ids['specialty']})
            c.execute(text("""INSERT INTO proveedor_coberturas(id,proveedor_id,provincia,localidad,cubre_toda_localidad)
                VALUES (:id,:provider,'Córdoba',:city,true)"""),
                {'id':ids['coverage'],'provider':ids['provider'],'city':city})
            c.execute(text("""INSERT INTO reclamos(id,numero,descripcion,urgencia,inquilino_id,propiedad_id,operador_asignado_id,tipo_id)
                VALUES (:id,:number,'Reclamo ficticio QA HU23: pérdida de agua.','media',:tenant,:property,:operator,:specialty)"""),
                {'id':ids['claim'],'number':900_000_000_000+ids['claim'].int%10**12,'tenant':ids['tenant'],
                 'property':ids['property'],'operator':users['operador'].id,'specialty':ids['specialty']})
            factory=sessionmaker(bind=c,class_=RollbackSession,join_transaction_mode='create_savepoint')
            yield SimpleNamespace(connection=c,factory=factory,users=users,password=password,ids=ids)
        finally:
            tx.rollback()
            # Misma instantánea: ningún conteo ni last_value debe variar por QA.
            assert inventory(c)==before,'La prueba no debe conservar filas ni consumir secuencias.'
            assert c.execute(text('SELECT count(*) FROM reclamos WHERE id=:id'),{'id':ids['claim']}).scalar_one()==0


@pytest.mark.parametrize('expense',['ordinario','extraordinario'])
@pytest.mark.parametrize('negotiate',[False,True])
def test_real_login_to_visit_and_rollback(monkeypatch,expense,negotiate):
    monkeypatch.setenv('AARI_QUOTE_PORTAL_ENABLED','true')
    monkeypatch.setenv('AARI_VISITS_ENABLED','true')
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED','true')
    def forbidden(*args,**kwargs): raise AssertionError('No se permiten envíos externos en QA.')
    monkeypatch.setattr('app.services.claim_notifications.SmtpClaimEmailSender.send',forbidden)
    with synthetic_case() as case:
        claim=case.ids['claim']
        actor=case.users['inquilino' if expense=='ordinario' else 'propietario']
        claims=SqlAlchemyClaimsRepository(case.factory)
        claims.persist_classification(claim,AgentClassificationResult(tipo_gasto=expense,confianza=.95,
            fundamento='Resultado sintético autorizado para QA, sin LLM.',debe_escalar=False,motivo_escalado=None,
            estado_clasificacion='clasificado',actor_responsable=actor.rol,notificacion_responsable_requerida=True))
        if expense=='extraordinario':
            authorization=SqlAlchemyExpenseAuthorizationsRepository(case.factory)
            authorization.decide(claim,actor,ExpenseDecisionRequest(request_id=uuid4(),
                expected_updated_at=authorization.get(claim,actor).updated_at),decision='autorizar')
        choices=SqlAlchemyProviderChoicesRepository(case.factory)
        view=choices.get(claim,actor)
        choices.choose(claim,actor,ProviderChoiceRequest(request_id=uuid4(),solicitud_id=view.solicitud_id,
            expected_updated_at=view.updated_at,tipo_proveedor='fidelizado'))
        portal=SqlAlchemyQuotePortal(case.factory,scope_claim_id=claim)
        portal.publish(claim)
        request_id=portal.list_own(case.users['proveedor'])['items'][0]['id']
        portal.submit(request_id,case.users['proveedor'],PortalQuoteRequest(request_id=uuid4(),monto='10000.50',
            moneda='ARS',tipo_importe='minimo' if negotiate else 'exacto',descripcion='Reparación sintética de QA.'))
        selections=SqlAlchemyQuoteSelections(case.factory)
        visit_repo=SqlAlchemyVisits(case.factory)
        app=FastAPI()
        for router in (auth.router,quote_selections.router,visits.router,conversations.router): app.include_router(router)
        service=AuthService(SqlAlchemyUsuariosRepository(case.factory),SqlAlchemyAccessRepository(case.factory))
        app.dependency_overrides[auth.get_auth_service]=lambda:service
        app.dependency_overrides[quote_selections.get_quote_selections]=lambda:selections
        app.dependency_overrides[visits.get_visits]=lambda:visit_repo
        app.dependency_overrides[conversations.get_conversations]=lambda:SqlAlchemyConversations(case.factory)
        assert auth.get_current_user not in app.dependency_overrides
        path=f'/reclamos/{claim}/visita'
        selection_path=f'/reclamos/{claim}/seleccion-presupuesto'
        with TestClient(app) as http:
            assert http.get(path).status_code==401
            def login(user):
                http.cookies.clear()
                result=http.post('/auth/login',json={'email':user.email,'password':case.password})
                assert result.status_code==200 and result.json()['user']['rol']==user.rol
                assert http.get('/auth/me').status_code==200
                assert 'httponly' in result.headers['set-cookie'].lower()
            def command(role,action,extra=None):
                login(case.users[role])
                current=http.get(path).json()
                payload={'request_id':str(uuid4()),'coordinacion_id':current['id'],
                    'version_esperada':current['version'],**(extra or {})}
                response=http.post(path+'/'+action,json=payload)
                assert response.status_code==200
                return response.json()
            login(actor)
            view=http.get(selection_path).json()
            selected=http.post(selection_path,json={'request_id':str(uuid4()),'ronda_id':str(view['ronda_id']),
                'expected_updated_at':view['updated_at'],'modalidad':'fidelizado','presupuesto_id':view['items'][0]['id']})
            assert selected.status_code==200
            # Sólo el reclamo ficticio: no tick() global sobre registros compartidos.
            assert visit_repo.start(claim)
            start=(datetime.now(timezone.utc)+timedelta(days=4)).replace(hour=17,minute=0,second=0,microsecond=0)
            slots=[{'desde':(start+timedelta(days=n)).isoformat(),'hasta':(start+timedelta(days=n,hours=2)).isoformat()} for n in range(3)]
            published=command('inquilino','disponibilidad',{'opciones':slots})
            if negotiate:
                command('proveedor','sin-coincidencia')
                proposed=command('inquilino','proponer',{'fecha':(start+timedelta(days=7)).isoformat()})
                result=command('proveedor','confirmar',{'propuesta_version':proposed['propuesta']['version']})
            else: result=command('proveedor','confirmar',{'fecha':slots[0]['desde']})
            assert result['etapa']=='confirmada' and result['vence_en']==published['vence_en']
            login(case.users['inquilino'])
            assert http.get(path).json()['fecha_confirmada']
            assert case.connection.execute(text('SELECT count(*) FROM visitas WHERE reclamo_id=:id'),{'id':claim}).scalar_one()==1
