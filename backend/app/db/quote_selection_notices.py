"""HU20: no entregar un aviso de selección que ya dejó de estar vigente."""

from sqlalchemy import text


def selection_notices_available(session):
    return session.bind.dialect.name == 'postgresql' and session.execute(text(
        "SELECT to_regclass('public.reclamo_selecciones_presupuesto') IS NOT NULL"
    )).scalar_one()


SELECT_NOTICE = '''SELECT n.id, coalesce((r.estado='Proveedor seleccionado'
    AND r.presupuesto_seleccionado_id=sp.presupuesto_id AND r.proveedor_seleccionado_id=sp.proveedor_id
    AND r.monto_seleccionado=sp.monto AND p.activo AND p.usuario_id=q.usuario_id
    AND u.activo AND NOT u.primer_ingreso AND u.rol::text='proveedor'
    AND p.email=u.email AND n.destinatario_contacto=p.email
    AND n.destinatario_tipo='proveedor' AND n.canal='email'),false) AS vigente
    FROM notificaciones n
    LEFT JOIN reclamo_selecciones_presupuesto sp
        ON n.clave_idempotencia='hu20:'||sp.id::text||':'||'seleccion' AND n.reclamo_id=sp.reclamo_id
    LEFT JOIN reclamos r ON r.id=sp.reclamo_id
    LEFT JOIN presupuestos b ON b.id=sp.presupuesto_id
    LEFT JOIN aari_solicitudes_presupuesto q ON q.id=b.solicitud_aari_id
    LEFT JOIN proveedores p ON p.id=sp.proveedor_id LEFT JOIN usuarios u ON u.id=q.usuario_id
    WHERE n.clave_idempotencia LIKE 'hu20:%' '''


def _cancel(session, notice_id):
    session.execute(text('''UPDATE notificaciones SET estado_envio='fallido',
        ultimo_error='Selección o destinatario no vigente; aviso HU20 cancelado.',
        proximo_intento_en=NULL,bloqueado_hasta=NULL,updated_at=clock_timestamp()
        WHERE id=:id AND estado_envio IN ('pendiente','procesando')'''), {'id': notice_id})


def cancel_obsolete_selection_notices(session, *, notification_id=None):
    if not selection_notices_available(session):
        return
    rows = session.execute(text(SELECT_NOTICE + " AND n.estado_envio IN ('pendiente','procesando')"
        + (' AND n.id=:id' if notification_id else '')), {'id': notification_id}).mappings().all()
    for row in rows:
        if not row['vigente']:
            _cancel(session, row['id'])


def validate_selection_notice(session, notification_id):
    if not selection_notices_available(session):
        return True
    row = session.execute(text(SELECT_NOTICE + ' AND n.id=:id'), {'id': notification_id}).mappings().one_or_none()
    if row is None or row['vigente']:
        return True
    _cancel(session, notification_id)
    return False
