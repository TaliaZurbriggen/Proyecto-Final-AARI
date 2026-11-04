"""Revalidar destinatarios HU24 justo antes de SMTP, sin reenviar una selección."""

from sqlalchemy import text


def validate_cancellation_notice(session, notification_id):
    if session.bind.dialect.name!='postgresql':
        return True
    key=session.execute(text('SELECT clave_idempotencia FROM notificaciones WHERE id=:id'),
                        {'id':notification_id}).scalar_one_or_none()
    if not key or not key.startswith('hu24:'):
        return True
    valid=session.execute(text('''SELECT EXISTS(
        SELECT 1 FROM notificaciones n JOIN cancelaciones c ON n.reclamo_id=c.reclamo_id
        JOIN usuarios u ON u.email=n.destinatario_contacto AND u.activo AND NOT u.primer_ingreso
        WHERE n.id=:id AND n.canal='email' AND (
            (n.clave_idempotencia='hu24:'||c.id::text||':'||'alerta'
                AND u.rol::text IN ('operador','administrador')) OR EXISTS(
                SELECT 1 FROM proveedores p WHERE p.usuario_id=u.id AND p.activo
                  AND p.email=u.email AND u.rol::text='proveedor'
                  AND n.clave_idempotencia='hu24:'||c.id::text||':proveedor:'||p.id::text)))'''),
        {'id':notification_id}).scalar_one()
    if valid:
        return True
    session.execute(text('''UPDATE notificaciones SET estado_envio='fallido',proximo_intento_en=NULL,
        bloqueado_hasta=NULL,ultimo_error='Destinatario de cancelación no vigente.' WHERE id=:id'''),
        {'id':notification_id})
    return False
