"""Plazos HU17. Se ejecutan desde el worker existente; nunca desde GET."""

from sqlalchemy import text

from app.services.responsible_actor_notifications import provider_choice_url


CURRENT_STAGE = """ep.solicitud_responsable_en=rr.solicitado_en AND ep.actor_tipo=rr.actor_tipo AND (
    (r.tipo_gasto='ordinario' AND ep.actor_tipo='inquilino'
     AND r.estado='Pendiente de respuesta del responsable')
    OR (r.tipo_gasto='extraordinario' AND ep.actor_tipo='propietario' AND r.estado='Autorizado'))"""


def choices_available(session):
    # Permite desplegar primero el código sin alterar los jobs HU12/HU16 previos.
    return session.bind.dialect.name == "postgresql" and session.execute(text(
        "SELECT to_regclass('public.reclamo_elecciones_proveedor') IS NOT NULL")).scalar_one()


def activate_existing(session, limit):
    """Descubrir solicitudes previas sin rejuvenecer sus fechas ni tocar estados."""
    rows = session.execute(text("""
        SELECT r.id,rr.solicitado_en,rr.actor_tipo,
            CASE WHEN r.tipo_gasto='ordinario' THEN rr.solicitado_en ELSE a.decidido_en END AS started
        FROM reclamos r JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
        LEFT JOIN reclamo_autorizaciones a ON a.reclamo_id=r.id AND a.solicitado_en=rr.solicitado_en
            AND a.decision='autorizar'
        WHERE ((r.tipo_gasto='ordinario' AND rr.actor_tipo='inquilino'
                AND r.estado='Pendiente de respuesta del responsable')
            OR (r.tipo_gasto='extraordinario' AND rr.actor_tipo='propietario'
                AND r.estado='Autorizado' AND a.request_id IS NOT NULL))
          AND NOT EXISTS (SELECT 1 FROM reclamo_elecciones_proveedor ep
                          WHERE ep.reclamo_id=r.id AND ep.solicitud_responsable_en=rr.solicitado_en)
        ORDER BY rr.solicitado_en,r.id FOR UPDATE OF r SKIP LOCKED LIMIT :limit
    """), {"limit": limit}).mappings().all()
    for row in rows:
        session.execute(text("""
            INSERT INTO reclamo_elecciones_proveedor (reclamo_id,solicitud_responsable_en,actor_tipo,
                solicitado_en,recordatorio_programado_en,respuesta_vence_en)
            VALUES (:id,:solicitado_en,:actor_tipo,:started,:started+interval '48 hours',:started+interval '72 hours')
            ON CONFLICT (reclamo_id,solicitud_responsable_en) DO NOTHING
        """), dict(row))


def enqueue_choice_followups(session, *, limit, operator_recipient):
    activate_existing(session, limit)
    rows = session.execute(text(f"""
        SELECT r.id FROM reclamos r JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
        JOIN reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
        WHERE ep.estado='pendiente' AND {CURRENT_STAGE}
          AND (ep.respuesta_vence_en<=clock_timestamp()
            OR (ep.recordatorio_generado_en IS NULL AND ep.recordatorio_programado_en<=clock_timestamp()))
        ORDER BY ep.respuesta_vence_en,r.id FOR UPDATE OF r SKIP LOCKED LIMIT :limit
    """), {"limit": limit}).scalars().all()
    enqueued = 0
    for claim in rows:
        row = session.execute(text(f"""
            SELECT ep.*,r.numero,r.estado AS estado_reclamo,r.operador_asignado_id,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.email ELSE pr.email END AS email,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.telefono ELSE pr.telefono END AS telefono,
                CASE WHEN ep.actor_tipo='inquilino' THEN i.canal_notificacion ELSE pr.canal_notificacion END AS canal
            FROM reclamos r JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
            JOIN reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
            JOIN inquilinos i ON i.id=r.inquilino_id
            JOIN propiedades p ON p.id=r.propiedad_id JOIN propietarios pr ON pr.id=p.propietario_id
            WHERE r.id=:claim AND ep.estado='pendiente' AND {CURRENT_STAGE}
            FOR UPDATE OF rr,ep
        """), {"claim": claim}).mappings().one_or_none()
        if row is None:
            continue
        now = session.execute(text("SELECT clock_timestamp()")).scalar_one()
        expired = now >= row["respuesta_vence_en"]
        if expired:
            session.execute(text("SELECT set_config('app.origen_reclamo','sistema',true)"))
            session.execute(text("SELECT set_config('app.usuario_reclamo','',true)"))
            session.execute(text("SELECT set_config('app.omitir_notificacion_inquilino','false',true)"))
            session.execute(text("UPDATE reclamos SET estado='Pendiente de respuesta - vencido' WHERE id=:claim"), {"claim": claim})
            session.execute(text("UPDATE reclamo_elecciones_proveedor SET estado='vencida' WHERE id=:id"), {"id": row["id"]})
            operator = operator_recipient(session, assigned_operator_id=row["operador_asignado_id"])
            if operator is None:
                # El estado vencido persiste aunque no exista ninguna cuenta operativa.
                continue
            role, contact, channel = operator["rol"], operator["email"], "email"
            event = "eleccion_proveedor_vencido"
            notification_state = "Pendiente de respuesta - vencido"
            message = f"El reclamo #{row['numero']:06d} agotó las 72 h para elegir tipo de proveedor. Requiere intervención operativa."
        else:
            if row["recordatorio_generado_en"] is not None or now < row["recordatorio_programado_en"]:
                continue
            role, channel = row["actor_tipo"], row["canal"]
            contact = row["email"] if channel == "email" else row["telefono"]
            event = "eleccion_proveedor_recordatorio"
            notification_state = row["estado_reclamo"]
            message = (f"El reclamo #{row['numero']:06d} espera tu elección de proveedor. "
                       f"El plazo vence el {row['respuesta_vence_en'].isoformat()}. "
                       f"Ingresá con tu cuenta: {provider_choice_url(claim, role)}")
            session.execute(text("UPDATE reclamo_elecciones_proveedor SET recordatorio_generado_en=:now WHERE id=:id"),
                            {"id": row["id"], "now": now})
        if not contact:
            continue
        result = session.execute(text("""
            INSERT INTO notificaciones (reclamo_id,destinatario_tipo,destinatario_contacto,canal,
                asunto,mensaje,tipo_evento,clave_idempotencia,solicitud_tipo_proveedor_id,
                estado_reclamo,estado_envio,proximo_intento_en)
            VALUES (:claim,:role,:contact,:channel,:subject,:message,:event,:key,:id,:state,'pendiente',CURRENT_TIMESTAMP)
            ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL DO NOTHING
        """), {"claim": claim, "role": role, "contact": contact, "channel": channel,
               "subject": f"AARI - Elección de proveedor en reclamo #{row['numero']:06d}",
               "message": message, "event": event, "key": f"{row['id']}:{event}", "id": row["id"], "state": notification_state})
        enqueued += max(result.rowcount, 0)
    return enqueued


def cancel_obsolete_choice_notices(session):
    session.execute(text(f"""
        UPDATE notificaciones n SET estado_envio='fallido',proximo_intento_en=NULL,bloqueado_hasta=NULL,
            ultimo_error='Elección finalizada o vencida; pedido inicial obsoleto.'
        WHERE n.destinatario_tipo='inquilino' AND n.tipo_evento IN ('responsable_inicial','responsable_recordatorio')
          AND n.estado_envio IN ('pendiente','procesando')
          AND EXISTS (SELECT 1 FROM reclamo_elecciones_proveedor ep WHERE ep.reclamo_id=n.reclamo_id)
          AND NOT EXISTS (
            SELECT 1 FROM reclamo_elecciones_proveedor ep JOIN reclamos r ON r.id=ep.reclamo_id
            JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
            WHERE ep.reclamo_id=n.reclamo_id AND ep.estado='pendiente'
              AND {CURRENT_STAGE} AND ep.respuesta_vence_en>clock_timestamp())
    """))
    session.execute(text(f"""
        UPDATE notificaciones n SET estado_envio='fallido',proximo_intento_en=NULL,bloqueado_hasta=NULL,
            ultimo_error='Elección finalizada o vencida; recordatorio obsoleto.'
        WHERE n.tipo_evento='eleccion_proveedor_recordatorio' AND n.estado_envio IN ('pendiente','procesando')
          AND NOT EXISTS (
            SELECT 1 FROM reclamo_elecciones_proveedor ep JOIN reclamos r ON r.id=ep.reclamo_id
            JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
            WHERE ep.id=n.solicitud_tipo_proveedor_id AND ep.estado='pendiente'
              AND {CURRENT_STAGE} AND ep.respuesta_vence_en>clock_timestamp())
    """))
