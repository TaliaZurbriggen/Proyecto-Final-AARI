"""Canal AARI con PostgreSQL local descartable; no aplica migraciones de Meta."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.quote_portal import SqlAlchemyQuotePortal
from app.schemas.auth import AuthenticatedUser
from app.schemas.quote_portal import PortalQuoteRequest
from app.services.quote_portal import QuotePortalError
from tests.test_provider_choices_postgres import choice_base, prepare, body as choice_body
from tests.test_responsible_actor_postgres import claim_case, local_engine, MIGRATIONS
from tests.test_quote_requests_postgres import provider, eligible


pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='Sólo PostgreSQL local descartable.')


@pytest.fixture
def portal_case(choice_base,monkeypatch):
    monkeypatch.setenv('APP_LOGIN_URL','https://aari.example/login')
    case=choice_base
    for name in ('15_proveedores_cobertura_horario.sql','16_finalizar_cobertura_proveedores.sql',
                 '20261009120000_hu15_proveedores_candidatos.sql','20261026180000_hu32_rol_proveedor.sql',
                 '20261026180100_hu32_acceso_proveedor.sql','20261027130000_hu19_canal_aari.sql'):
        with case.db.connect() as c:
            cursor=c.connection.cursor()
            cursor.execute((MIGRATIONS/name).read_text(encoding='utf-8'))
            c.connection.commit()
            cursor.close()
    with case.db.begin() as c:
        case.specialty=c.execute(text("INSERT INTO especialidades(nombre) VALUES ('Servicio Sintetico') RETURNING id")).scalar_one()
        c.execute(text('UPDATE reclamos SET tipo_id=:type WHERE id=:id'),{'type':case.specialty,'id':case.claim})
        c.execute(text("UPDATE propiedades SET barrio='Centro'"))
    case.portal=SqlAlchemyQuotePortal(sessionmaker(bind=case.db),scope_claim_id=case.claim)
    return case


def active_provider(case,n=0,**kwargs):
    pid=provider(case,phone=f'+15555551{n:03d}',**kwargs)
    email=f'service{n}@example.com'
    with case.db.begin() as c:
        uid=c.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso) VALUES (:email,'unused','proveedor',false) RETURNING id"),{'email':email}).scalar_one()
        c.execute(text('UPDATE proveedores SET usuario_id=:user,email=:email WHERE id=:id'),{'user':uid,'email':email,'id':pid})
    return AuthenticatedUser(id=uid,email=email,rol='proveedor',primer_ingreso=False,perfil_id=pid)


def budget(**changes):
    return PortalQuoteRequest(request_id=uuid4(),monto='10000.50',moneda='ARS',tipo_importe='minimo',
                              descripcion='Reparación de cañería con materiales',**changes)


def request(case,user): return case.portal.list_own(user,status='todas')['items'][0]


def scalar(case,sql,**params):
    with case.db.connect() as c: return c.execute(text(sql),params).scalar_one()


def past_deadline(case):
    with case.db.begin() as c:
        c.execute(text("UPDATE aari_rondas_presupuesto SET publicada_en=clock_timestamp()-interval '25 hours',vence_en=clock_timestamp()-interval '1 hour'"))
        c.execute(text("UPDATE aari_solicitudes_presupuesto SET publicada_en=clock_timestamp()-interval '25 hours',vence_en=clock_timestamp()-interval '1 hour'"))


@pytest.mark.parametrize('expense',['ordinario','extraordinario'])
def test_publish_eligible_private_requests_once_and_minimal_mail(portal_case,expense):
    case=eligible(portal_case,expense)
    users=[active_provider(case,n) for n in range(2)]
    provider(case,phone='+15555550200')  # Sin cuenta: no es silencio del proveedor.
    active_provider(case,3,city='Otra ciudad')
    first=case.portal.publish(case.claim)
    assert first['publicadas']==2 and first['excluidas']==1
    assert case.portal.publish(case.claim)['repetida']
    assert scalar(case,'SELECT count(*) FROM aari_solicitudes_presupuesto')==2
    row=request(case,users[0])
    assert row['puede_responder'] and (row['vence_en']-row['publicada_en']).total_seconds()==86400
    with case.db.connect() as c:
        mail=c.execute(text("SELECT mensaje FROM notificaciones WHERE destinatario_tipo='proveedor' LIMIT 1")).scalar_one()
        assert '/proveedor/solicitudes/' in mail and 'Unidad de prueba' not in mail and 'example.com' not in mail
        assert c.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_name='proveedor_solicitudes_presupuesto'")).scalar_one()==0


@pytest.mark.parametrize('condition',['no_choice','own','no_authorization','closed','inactive_actor','first_login','tenant_left'])
def test_non_eligible_does_not_publish(portal_case,condition):
    case=portal_case
    if condition=='no_authorization': prepare(case,'extraordinario',authorize=False)
    elif condition=='no_choice': prepare(case)
    else: eligible(case,choice='propio' if condition=='own' else 'fidelizado')
    active_provider(case)
    with case.db.begin() as c:
        if condition=='closed': c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
        elif condition=='inactive_actor': c.execute(text('UPDATE usuarios SET activo=false WHERE id=:id'),{'id':case.actor.id})
        elif condition=='first_login': c.execute(text('UPDATE usuarios SET primer_ingreso=true WHERE id=:id'),{'id':case.actor.id})
        elif condition=='tenant_left': c.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada'"))
    assert case.portal.discover_portal()==0
    assert scalar(case,'SELECT count(*) FROM aari_rondas_presupuesto')==0


@pytest.mark.parametrize('kind',['exacto','minimo'])
def test_structured_quote_replay_and_single_actor_notice(portal_case,kind):
    case=eligible(portal_case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    rid=request(case,user)['id']
    data=budget().model_copy(update={'tipo_importe':kind})
    first=case.portal.submit(rid,user,data)
    assert first['estado']=='respondida' and first['presupuesto']['tipo_importe']==kind
    assert first['presupuesto']['monto']=='10000.50'
    assert case.portal.submit(rid,user,data)==first
    with pytest.raises(QuotePortalError): case.portal.submit(rid,user,budget())
    assert scalar(case,'SELECT count(*) FROM presupuestos')==1
    assert scalar(case,'SELECT count(*) FROM notificaciones WHERE clave_idempotencia LIKE :pattern',pattern='aari-quote:%:disponible')==1
    result=case.portal.for_claim(case.claim,case.actor)['items'][0]
    assert result['presupuesto']['tipo_importe']==kind and 'aviso_estado' not in result


def test_one_provider_cannot_read_or_submit_another_request(portal_case):
    case=eligible(portal_case)
    first,second=active_provider(case),active_provider(case,1)
    case.portal.publish(case.claim)
    rid=request(case,first)['id']
    for operation in (lambda:case.portal.get_own(rid,second),lambda:case.portal.submit(rid,second,budget())):
        with pytest.raises(QuotePortalError) as error: operation()
        assert error.value.status==404
    assert scalar(case,'SELECT count(*) FROM presupuestos')==0


@pytest.mark.parametrize('change',['inactive','specialty','coverage','description','choice'])
def test_changed_context_prevents_response(portal_case,change):
    case=eligible(portal_case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    rid=request(case,user)['id']
    with case.db.begin() as c:
        if change=='inactive': c.execute(text('UPDATE proveedores SET activo=false'))
        elif change=='specialty': c.execute(text('DELETE FROM proveedor_especialidades'))
        elif change=='coverage': c.execute(text("UPDATE proveedor_coberturas SET localidad='Otra ciudad'"))
        elif change=='description': c.execute(text("UPDATE reclamos SET descripcion='Otro problema sintético completamente diferente'"))
        elif change=='choice': c.execute(text("UPDATE reclamos SET estado='Resuelto'"))
    with pytest.raises(QuotePortalError): case.portal.submit(rid,user,budget())
    assert scalar(case,'SELECT count(*) FROM presupuestos')==0
    assert case.portal.list_own(user)['total']==0


def test_two_publishers_and_two_answers_do_not_duplicate(portal_case):
    case=eligible(portal_case)
    user=active_provider(case)
    barrier=Barrier(2)
    def publish(_):
        barrier.wait(timeout=5)
        return case.portal.publish(case.claim)
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(publish,range(2)))
    assert scalar(case,'SELECT count(*) FROM aari_solicitudes_presupuesto')==1
    rid=request(case,user)['id']
    barrier=Barrier(2)
    def send(_):
        barrier.wait(timeout=5)
        try: return case.portal.submit(rid,user,budget())
        except QuotePortalError: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(send,range(2)))
    assert sum(r is not None for r in results)==1
    assert scalar(case,'SELECT count(*) FROM presupuestos')==1
    assert scalar(case,"SELECT count(*) FROM aari_presupuesto_eventos WHERE tipo='presupuesto_registrado'")==1


def test_partial_quotes_and_delivery_failure_do_not_erase_results(portal_case):
    case=eligible(portal_case)
    users=[active_provider(case,n) for n in range(2)]
    case.portal.publish(case.claim)
    case.portal.submit(request(case,users[0])['id'],users[0],budget())
    past_deadline(case)
    assert case.portal.finalize_due_portal()==1
    assert scalar(case,'SELECT estado FROM aari_rondas_presupuesto')=='disponibles'
    assert scalar(case,'SELECT count(*) FROM presupuestos')==1
    assert case.portal.finalize_due_portal()==0
    with pytest.raises(QuotePortalError): case.portal.submit(request(case,users[1])['id'],users[1],budget())


@pytest.mark.parametrize('sent',[True,False])
def test_zero_quotes_distinguishes_smtp_failure_from_silence(portal_case,sent):
    case=eligible(portal_case)
    active_provider(case)
    case.portal.publish(case.claim)
    with case.db.begin() as c:
        c.execute(text("UPDATE notificaciones SET estado_envio=:state WHERE destinatario_tipo='proveedor'"),{'state':'enviado' if sent else 'fallido'})
    past_deadline(case)
    case.portal.finalize_due_portal()
    assert scalar(case,'SELECT estado FROM aari_rondas_presupuesto')==('sin_presupuestos' if sent else 'revision')
    assert scalar(case,'SELECT estado FROM reclamos')==('Sin presupuestos recibidos' if sent else 'Pendiente de asignación')


def test_all_unactivated_is_review_without_starting_a_fake_deadline(portal_case):
    case=eligible(portal_case)
    provider(case)
    assert case.portal.publish(case.claim)['publicadas']==0
    assert scalar(case,'SELECT estado FROM aari_rondas_presupuesto')=='revision'
    assert scalar(case,'SELECT vence_en FROM aari_rondas_presupuesto') is None


def test_many_providers_pagination_no_competitor_data(portal_case):
    case=eligible(portal_case)
    users=[active_provider(case,n) for n in range(30)]
    assert case.portal.publish(case.claim)['publicadas']==30
    data=case.portal.list_own(users[0],1,10)
    assert data['total']==len(data['items'])==1
    assert case.portal.list_own(users[0],2,10)['items']==[]
    assert 'proveedor' not in data['items'][0] and 'aviso_estado' not in data['items'][0]


def test_migration_guards_price_source_and_rls(portal_case):
    case=eligible(portal_case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    rid=request(case,user)['id']
    with pytest.raises(IntegrityError),case.db.begin() as c:
        c.execute(text("""INSERT INTO presupuestos(reclamo_id,proveedor_id,monto,moneda,tipo_importe,
            descripcion,solicitud_aari_id,presentado_por) VALUES (:claim,:provider,100,'ARS','minimo',
            'Trabajo sintético detallado',:request,:wrong)"""),
            {'claim':case.claim,'provider':user.perfil_id,'request':rid,'wrong':case.actor.id})
    for table in ('aari_rondas_presupuesto','aari_solicitudes_presupuesto','aari_presupuesto_eventos','presupuestos'):
        assert scalar(case,'SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:t AS regclass)',t=table)
        for role in ('anon','authenticated'):
            assert not scalar(case,"SELECT has_table_privilege(:role,:t,'SELECT,INSERT,UPDATE,DELETE')",role=role,t=table)


def test_failure_of_audit_rolls_back_publication(portal_case):
    case=eligible(portal_case)
    active_provider(case)
    with case.db.begin() as c:
        c.exec_driver_sql("""CREATE FUNCTION hu19_fail() RETURNS trigger LANGUAGE plpgsql AS
            $$ BEGIN RAISE EXCEPTION 'synthetic audit error'; END $$;
            CREATE TRIGGER hu19_fail BEFORE INSERT ON aari_presupuesto_eventos FOR EACH ROW EXECUTE FUNCTION hu19_fail();""")
    with pytest.raises(SQLAlchemyError): case.portal.publish(case.claim)
    assert scalar(case,'SELECT count(*) FROM aari_rondas_presupuesto')==0
    assert scalar(case,"SELECT count(*) FROM notificaciones WHERE destinatario_tipo='proveedor'")==0


def test_real_outbox_with_mock_smtp_preserves_publication_and_deadline(portal_case):
    from app.services.claim_notifications import ClaimNotificationService, ClaimEmailDeliveryError
    case=eligible(portal_case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    before=request(case,user)
    notice=scalar(case,'SELECT aviso_id FROM aari_solicitudes_presupuesto')
    class Sender:
        failed=True
        calls=0
        def send(self,**kwargs):
            self.calls+=1
            assert kwargs['recipient']==user.email and '/proveedor/solicitudes/' in kwargs['message']
            if self.failed: raise ClaimEmailDeliveryError('Fallo sintético de SMTP')
    sender=Sender()
    service=ClaimNotificationService(case.claims,sender)
    assert not service.deliver(notice)
    assert request(case,user)==before
    with case.db.begin() as c:
        c.execute(text("UPDATE notificaciones SET proximo_intento_en=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':notice})
    sender.failed=False
    assert service.deliver(notice)
    assert request(case,user)==before
    assert not service.deliver(notice) and sender.calls==2


def test_late_replay_returns_original_but_new_answer_cannot_replace_it(portal_case):
    case=eligible(portal_case)
    user=active_provider(case)
    case.portal.publish(case.claim)
    rid=request(case,user)['id']
    data=budget()
    before=case.portal.submit(rid,user,data)['presupuesto']
    past_deadline(case)
    case.portal.finalize_due_portal()
    assert case.portal.submit(rid,user,data)['presupuesto']==before
    with pytest.raises(QuotePortalError): case.portal.submit(rid,user,budget())


def test_only_current_responsible_and_assigned_agency_can_see_budgets(portal_case):
    case=eligible(portal_case)
    active_provider(case)
    case.portal.publish(case.claim)
    other=case.actors['propietario']
    with pytest.raises(QuotePortalError) as error: case.portal.for_claim(case.claim,other)
    assert error.value.status==404
    with case.db.begin() as c:
        uid=c.execute(text("INSERT INTO usuarios(email,password_hash,rol,primer_ingreso,nombre_completo) VALUES ('hu19-other-operator@example.com','unused','operador',false,'Otro Operador Sintetico') RETURNING id")).scalar_one()
    actor=AuthenticatedUser(id=uid,email='hu19-other-operator@example.com',rol='operador',primer_ingreso=False)
    with pytest.raises(QuotePortalError): case.portal.for_claim(case.claim,actor)
    with case.db.begin() as c: c.execute(text('UPDATE reclamos SET operador_asignado_id=:user WHERE id=:id'),{'user':uid,'id':case.claim})
    assert 'aviso_estado' in case.portal.for_claim(case.claim,actor)['items'][0]
    with case.db.begin() as c: c.execute(text("UPDATE inquilinos SET propiedad_id=NULL,estado='sin_propiedad_asignada'"))
    with pytest.raises(QuotePortalError): case.portal.for_claim(case.claim,case.actor)


def test_filters_apply_before_count_and_pagination_with_real_mixed_requests(portal_case,monkeypatch):
    case=portal_case
    user,other=active_provider(case),active_provider(case,1)
    expected_pending=set()
    expected_sent=set()
    for index in range(31):
        child=SimpleNamespace(**vars(case))
        if index:
            with case.db.begin() as c:
                # Un reclamo activo por inquilino/propiedad: datos independientes,
                # sin quitar ni relajar restricciones del esquema real.
                prop=c.execute(text('''INSERT INTO propiedades
                    (direccion,provincia,localidad,barrio,tipo,propietario_id)
                    SELECT :address,provincia,localidad,barrio,tipo,propietario_id
                    FROM propiedades WHERE id=(SELECT propiedad_id FROM reclamos WHERE id=:id)
                    RETURNING id'''),{'address':f'Unidad sintética {index}','id':case.claim}).scalar_one()
                email=f'tenant-filter-{index}@example.com'
                uid=c.execute(text("""INSERT INTO usuarios(email,password_hash,rol,primer_ingreso)
                    VALUES (:email,'unused','inquilino',false) RETURNING id"""),{'email':email}).scalar_one()
                tenant=c.execute(text('''INSERT INTO inquilinos
                    (nombre_completo,dni,email,telefono,propiedad_id,usuario_id)
                    VALUES ('Inquilino Sintetico',:dni,:email,'00000000',:prop,:user) RETURNING id'''),
                    {'dni':f'8000{index:04d}','email':email,'prop':prop,'user':uid}).scalar_one()
                child.claim=c.execute(text('''INSERT INTO reclamos
                    (descripcion,urgencia,inquilino_id,propiedad_id,tipo_id)
                    SELECT descripcion,urgencia,:tenant,:prop,tipo_id FROM reclamos
                    WHERE id=:id RETURNING id'''),{'id':case.claim,'tenant':tenant,'prop':prop}).scalar_one()
                child.actors={**case.actors,'inquilino':AuthenticatedUser(id=uid,email=email,rol='inquilino',
                    primer_ingreso=False,perfil_id=tenant)}
        eligible(child)
        child.portal.publish(child.claim)
        rid=scalar(case,'SELECT id FROM aari_solicitudes_presupuesto WHERE reclamo_id=:claim AND usuario_id=:user',
                   claim=child.claim,user=user.id)
        if index<15:
            expected_pending.add(rid)
        elif index<27:
            child.portal.submit(rid,user,budget())
            expected_sent.add(rid)
        with case.db.begin() as c:
            if index==27:
                c.execute(text("""UPDATE aari_solicitudes_presupuesto
                    SET publicada_en=clock_timestamp()-interval '25 hours',vence_en=clock_timestamp()-interval '1 hour'
                    WHERE reclamo_id=:id"""),{'id':child.claim})
            elif index==28:
                c.execute(text("UPDATE aari_rondas_presupuesto SET estado='cancelada',cerrada_en=clock_timestamp() WHERE reclamo_id=:id"),{'id':child.claim})
            elif index==29:
                c.execute(text("UPDATE reclamos SET descripcion='Otro problema con contexto distinto de la solicitud' WHERE id=:id"),{'id':child.claim})
            elif index==30:
                c.execute(text("UPDATE reclamos SET estado='Resuelto' WHERE id=:id"),{'id':child.claim})
    for state,expected in [('pendientes',expected_pending),('enviadas',expected_sent)]:
        first=case.portal.list_own(user,1,10,status=state)
        second=case.portal.list_own(user,2,10,status=state)
        assert first['total']==second['total']==len(expected)
        assert len(first['items'])==10 and len(second['items'])==len(expected)-10
        assert {row['id'] for row in first['items']+second['items']}==expected
        assert case.portal.list_own(user,3,10,status=state)['items']==[]
        assert case.portal.list_own(user,1,10,status=state)==first
    assert case.portal.list_own(user)==case.portal.list_own(user,status='pendientes')
    assert case.portal.list_own(user,status='todas')['total']==31
    assert case.portal.list_own(other,status='enviadas')['total']==0
    assert scalar(case,'SELECT count(*) FROM presupuestos')==12
    lookups=[]
    candidates=case.portal._candidates
    def counted(session,row):
        lookups.append(row['id'])
        return candidates(session,row)
    monkeypatch.setattr(case.portal,'_candidates',counted)
    assert case.portal.list_own(user)['total']==15
    assert len(lookups)==1  # Mismos criterios: una búsqueda, no quince.
