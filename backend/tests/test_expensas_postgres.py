"""HU14 con SQL, triggers, reservas y RLS reales en PostgreSQL local descartable."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from app.db.expensas import SqlAlchemyExpensesRepository, enqueue_expense_report
from app.schemas.expensas import ExpenseFilters
from app.services.claim_notifications import ClaimEmailDeliveryError, ClaimNotificationService
from tests.test_responsible_actor_postgres import claim_case, classification, local_engine, make_due, snapshot


pytestmark=pytest.mark.skipif(not os.getenv('AARI_TEST_POSTGRES_URL'),reason='Solo PostgreSQL local dedicado.')


class Sender:
    def __init__(self, failures=0):
        self.failures=failures
        self.messages=[]

    def send(self,**message):
        self.messages.append(message)
        if len(self.messages)<=self.failures:
            raise ClaimEmailDeliveryError('No se pudo entregar la notificación por correo.')


def state(db,claim_id):
    with db.connect() as conn:
        return conn.execute(text('SELECT estado FROM reclamos WHERE id=:id'),{'id':claim_id}).scalar_one()


def due(db,notification_id):
    with db.begin() as conn:
        conn.execute(text("UPDATE notificaciones SET proximo_intento_en=CURRENT_TIMESTAMP - interval '1 minute' WHERE id=:id"),{'id':notification_id})


@pytest.mark.parametrize('failures',[0,1,2])
def test_expense_report_advances_only_after_valid_smtp_result(claim_case,failures):
    db,repo,claim_id=claim_case
    created=repo.persist_classification(claim_id,classification('expensa'))
    assert state(db,claim_id)=='Pendiente de respuesta del responsable'
    data=snapshot(db,claim_id)
    assert len(data['notificaciones'])==1 and data['notificaciones'][0]['tipo_evento']=='expensa_reporte'
    sender=Sender(failures)
    service=ClaimNotificationService(repo,sender)
    for attempt in range(failures+1):
        if attempt: due(db,created.notification_id)
        result=service.deliver(created.notification_id)
        assert result is (attempt==failures)
        if attempt<failures:
            assert state(db,claim_id)=='Pendiente de respuesta del responsable'
            assert not service.deliver(created.notification_id)  # No retry antes de 60s.
    assert state(db,claim_id)=='Derivado a inmobiliaria (expensa)'
    data=snapshot(db,claim_id)
    assert len(data['notificaciones'])==2
    assert len([n for n in data['notificaciones'] if n['destinatario_tipo']=='inquilino'])==1
    assert len(data['reclamo_historial_estados'])==2
    assert len(sender.messages)==failures+1
    assert 'Reporte de expensa' in sender.messages[0]['subject']
    assert not service.deliver(created.notification_id)


def test_three_failures_are_visible_and_do_not_advance_or_remind(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    sender=Sender(3)
    service=ClaimNotificationService(repo,sender)
    for i in range(3):
        if i: due(db,notification)
        assert service.deliver(notification) is False
    make_due(db,claim_id)
    assert repo.enqueue_due_responsible_followups(limit=10)==0
    assert service.deliver(notification) is False and len(sender.messages)==3
    assert state(db,claim_id)=='Pendiente de respuesta del responsable'
    api=SqlAlchemyExpensesRepository(sessionmaker(bind=db))
    result=api.list(ExpenseFilters(situacion='fallidos'))
    assert result.total==1 and result.fallidos==1 and result.items[0].intentos==3
    assert len(snapshot(db,claim_id)['notificaciones'])==1


@pytest.mark.parametrize('contact',[None,'invalid'])
def test_missing_or_invalid_configuration_preserves_report_without_smtp(claim_case,contact):
    db,repo,claim_id=claim_case
    with db.begin() as conn:
        if contact is None:
            conn.execute(text("DELETE FROM configuracion_sistema WHERE clave='correo_contacto_inmobiliaria'"))
        else:
            conn.execute(text("UPDATE configuracion_sistema SET valor=:contact WHERE clave='correo_contacto_inmobiliaria'"),{'contact':contact})
    assert repo.persist_classification(claim_id,classification('expensa')).notification_id is None
    data=SqlAlchemyExpensesRepository(sessionmaker(bind=db)).get(claim_id)
    assert data.entrega_estado=='configuracion_pendiente' and data.intentos==0
    assert data.reporte.numero and data.envios==[]
    assert snapshot(db,claim_id)['notificaciones']==[]


def test_snapshot_does_not_change_with_configuration_or_claim_edits(claim_case):
    db,repo,claim_id=claim_case
    created=repo.persist_classification(claim_id,classification('expensa'))
    api=SqlAlchemyExpensesRepository(sessionmaker(bind=db))
    original=api.get(claim_id).reporte
    with db.begin() as conn:
        conn.execute(text("UPDATE configuracion_sistema SET valor='other@example.com' WHERE clave='correo_contacto_inmobiliaria'"))
        conn.execute(text("UPDATE reclamos SET descripcion='Descripción posterior.' WHERE id=:id"),{'id':claim_id})
    assert api.get(claim_id).reporte==original
    with db.begin() as conn:
        assert enqueue_expense_report(conn,original,'other@example.com')==created.notification_id
    assert api.get(claim_id).envios[0].destinatario=='agency@example.com'
    assert len(snapshot(db,claim_id)['notificaciones'])==1


def test_stale_worker_is_ignored_and_recovered_attempt_finishes(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    first=repo.claim_notification(notification)
    with db.begin() as conn:
        conn.execute(text("UPDATE notificaciones SET bloqueado_hasta=CURRENT_TIMESTAMP - interval '1 second' WHERE id=:id"),{'id':notification})
    assert not repo.mark_notification_result(notification,attempt_number=first.attempt_number,sent=True)
    second=repo.claim_notification(notification)
    assert second.attempt_number==2
    assert not repo.mark_notification_result(notification,attempt_number=first.attempt_number,sent=True)
    assert repo.mark_notification_result(notification,attempt_number=second.attempt_number,sent=True)
    assert state(db,claim_id)=='Derivado a inmobiliaria (expensa)'


def test_interrupted_last_attempt_is_failed_without_advancing(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    for _ in range(3):
        context=repo.claim_notification(notification)
        assert context
        with db.begin() as conn:
            conn.execute(text("UPDATE notificaciones SET bloqueado_hasta=CURRENT_TIMESTAMP - interval '1 second' WHERE id=:id"),{'id':notification})
    assert repo.claim_notification(notification) is None
    assert SqlAlchemyExpensesRepository(sessionmaker(bind=db)).get(claim_id).entrega_estado=='fallido'
    assert state(db,claim_id)=='Pendiente de respuesta del responsable'


def test_two_workers_claim_only_one_report(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: repo.claim_notification(notification),range(2)))
    assert len([r for r in results if r])==1


def test_delivery_does_not_overwrite_an_advanced_claim(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    context=repo.claim_notification(notification)
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET estado='En proceso' WHERE id=:id"),{'id':claim_id})
    assert repo.mark_notification_result(notification,attempt_number=context.attempt_number,sent=True)
    assert state(db,claim_id)=='En proceso'


def test_reservation_expiring_while_waiting_for_claim_lock_is_ignored(claim_case):
    db,repo,claim_id=claim_case
    notification=repo.persist_classification(claim_id,classification('expensa')).notification_id
    context=repo.claim_notification(notification)
    waiting=Event()

    def reached_claim_lock(conn,cursor,statement,parameters,execution_context,executemany):
        if 'SELECT id FROM reclamos' in statement and 'FOR UPDATE' in statement:
            waiting.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with db.begin() as blocking:
                blocking.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'),{'id':claim_id})
                event.listen(db,'before_cursor_execute',reached_claim_lock)
                result=pool.submit(repo.mark_notification_result,notification,
                                   attempt_number=context.attempt_number,sent=True)
                assert waiting.wait(timeout=3)
                # La fecha es posterior al inicio de la transacción del worker.
                # CURRENT_TIMESTAMP conservaría ese inicio y aceptaría el resultado.
                with db.begin() as other:
                    other.execute(text('UPDATE notificaciones SET bloqueado_hasta=clock_timestamp() WHERE id=:id'),{'id':notification})
            assert result.result(timeout=3) is False
        finally:
            event.remove(db,'before_cursor_execute',reached_claim_lock)
    assert state(db,claim_id)=='Pendiente de respuesta del responsable'


def test_privilege_revocation_and_argentine_day_filters(claim_case):
    db,repo,claim_id=claim_case
    repo.persist_classification(claim_id,classification('expensa'))
    api=SqlAlchemyExpensesRepository(sessionmaker(bind=db))
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET creado_en='2026-10-01 03:00:00+00' WHERE id=:id"),{'id':claim_id})
        for table in ('reclamo_derivaciones_expensa','notas_internas','configuracion_sistema'):
            assert conn.execute(text('SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:table)'),{'table':table}).scalar_one()
            for role in ('anon','authenticated'):
                assert not conn.execute(text("SELECT has_table_privilege(:role,:table,'SELECT')"),{'role':role,'table':table}).scalar_one()
    filters=ExpenseFilters(situacion='todos',fecha_desde=date(2026,10,1),fecha_hasta=date(2026,10,1))
    assert api.list(filters).total==1
    with db.begin() as conn:
        conn.execute(text("UPDATE reclamos SET creado_en='2026-10-02 03:00:00+00' WHERE id=:id"),{'id':claim_id})
    assert api.list(filters).total==0


def test_expense_report_foreign_key_has_valid_covering_index(local_engine):
    with local_engine.connect() as conn:
        index = conn.execute(text("""
            SELECT i.indisvalid, i.indisready, i.indisunique,
                   ARRAY(
                       SELECT a.attname::text
                       FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
                       JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
                       ORDER BY k.position
                   ) AS columns
            FROM pg_index i
            WHERE i.indexrelid=to_regclass('public.idx_derivaciones_expensa_notificacion_reclamo')
              AND i.indrelid='public.reclamo_derivaciones_expensa'::regclass
        """)).mappings().one()
        assert index['indisvalid'] and index['indisready']
        assert index['indisunique'] is False  # La unicidad previa no se reemplaza.
        assert index['columns']==['notificacion_id','reclamo_id']
        assert conn.execute(text("""
            SELECT convalidated FROM pg_constraint
            WHERE conrelid='public.reclamo_derivaciones_expensa'::regclass
              AND conname='fk_derivacion_notificacion'
        """)).scalar_one() is True
