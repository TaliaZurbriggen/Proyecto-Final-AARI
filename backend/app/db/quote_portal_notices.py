"""Vigencia de avisos HU19; sin SMTP y sin depender de tablas del canal Meta."""

from sqlalchemy import text

from app.db.quote_requests import SqlAlchemyQuoteRequests
from app.services.quote_requests import request_content


OBSOLETE_NOTICE = 'Solicitud de presupuesto no vigente; aviso obsoleto cancelado.'


def portal_available(session):
    # El worker de correo también funciona antes de desplegar HU19.
    return session.bind.dialect.name == 'postgresql' and session.execute(text(
        "SELECT to_regclass('public.aari_solicitudes_presupuesto') IS NOT NULL"
    )).scalar_one()


NOTICE_SELECT = '''SELECT q.id,q.reclamo_id,q.proveedor_id,q.vence_en,rp.eleccion_id,rp.huella,
    n.id AS aviso_id, (rp.estado='esperando' AND rp.cerrada_en IS NULL
        AND q.vence_en>clock_timestamp() AND rp.vence_en>clock_timestamp()
        AND p.activo AND p.usuario_id=q.usuario_id AND u.activo AND NOT u.primer_ingreso
        AND u.rol::text='proveedor' AND u.email=p.email AND n.destinatario_contacto=p.email
        AND n.destinatario_tipo='proveedor' AND n.canal='email'
        AND NOT EXISTS (SELECT 1 FROM presupuestos b WHERE b.solicitud_aari_id=q.id)) AS habilitada
    FROM aari_solicitudes_presupuesto q
    JOIN aari_rondas_presupuesto rp ON rp.id=q.ronda_id
    JOIN proveedores p ON p.id=q.proveedor_id
    JOIN usuarios u ON u.id=q.usuario_id
    JOIN notificaciones n ON n.id=q.aviso_id'''


def notice_is_current(session, row):
    if not row['habilitada']:
        return False
    current = SqlAlchemyQuoteRequests._eligible(session, row['reclamo_id'])
    if (current is None or current['eleccion_id'] != row['eleccion_id']
            or request_content(current)[1] != row['huella']
            or row['proveedor_id'] not in SqlAlchemyQuoteRequests._candidates(session, current)):
        return False
    # La comprobación del reloj es posterior a la búsqueda de compatibilidad.
    return session.execute(text('''SELECT q.vence_en>clock_timestamp()
        AND rp.vence_en>clock_timestamp() AND rp.cerrada_en IS NULL AND rp.estado='esperando'
        FROM aari_solicitudes_presupuesto q JOIN aari_rondas_presupuesto rp ON rp.id=q.ronda_id
        WHERE q.id=:id'''), {'id':row['id']}).scalar_one()


def cancel_notice(session, notice_id):
    session.execute(text('''UPDATE notificaciones SET estado_envio='fallido',
        ultimo_error=:reason,proximo_intento_en=NULL,bloqueado_hasta=NULL,updated_at=clock_timestamp()
        WHERE id=:id AND estado_envio IN ('pendiente','procesando')'''),
        {'id':notice_id,'reason':OBSOLETE_NOTICE})


def cancel_obsolete_portal_notices(session, *, notification_id=None):
    if not portal_available(session):
        return
    scope = ' AND n.id=:id' if notification_id else ''
    rows = session.execute(text(NOTICE_SELECT+''' WHERE n.estado_envio IN ('pendiente','procesando')
        AND (n.proximo_intento_en<=clock_timestamp() OR n.estado_envio='procesando')'''+scope+' ORDER BY n.id'),
        {'id':notification_id}).mappings().all()
    for row in rows:
        if not notice_is_current(session, row):
            cancel_notice(session, row['aviso_id'])


def validate_portal_notice(session, notification_id):
    """True para otros avisos; HU19 revalida la solicitud enlazada, no el texto."""
    if not portal_available(session):
        return True
    row = session.execute(text(NOTICE_SELECT+' WHERE n.id=:id'),
                          {'id':notification_id}).mappings().one_or_none()
    if row is None:
        return True
    if notice_is_current(session, row):
        return True
    cancel_notice(session, notification_id)
    return False
