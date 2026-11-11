"""HU36: seguimiento de horarios confirmados bajo la reserva del reclamo."""
from datetime import timedelta

from sqlalchemy import text

from app.services.visits import ARGENTINA, VisitError, valid_time


PROPOSE = 'reprogramar'
DECIDE = 'decidir-reprogramacion'
REPORT = 'informar-ausencia'
FOLLOWUP_ACTIONS = {PROPOSE, DECIDE, REPORT}
DECISIONS = {'aceptar': 'aceptada', 'rechazar': 'rechazada', 'retirar': 'retirada'}


def schedule_event(event, revision):
    return f'{event}:horario:{revision}' if revision else event


def visit_time(value):
    return value.astimezone(ARGENTINA).strftime('%d/%m/%Y a las %H:%M')


def expire_proposal(session, row, now):
    session.execute(text('''UPDATE aari_visita_reprogramaciones SET estado='vencida', decidida_en=vence_en
        WHERE coordinacion_id=:id AND estado='pendiente' AND vence_en<=:now'''), {'id': row['id'], 'now': now})


def read_followup(session, row, user, roles, now, current):
    participant = roles['tenant'] or roles['provider']
    if 'version_horario' not in row or not row['visita_id'] or not (participant or roles['agency']):
        return None, []

    params = {'id': row['id'], 'now': now, 'user': user.id}
    proposals = session.execute(text('''SELECT id, fecha_anterior, fecha_propuesta, solicitante_rol, motivo,
            creada_en, vence_en, decision_rol, solicitante_id=:user AS propia,
            CASE WHEN estado='pendiente' AND vence_en<=:now THEN 'vencida' ELSE estado END AS estado,
            CASE WHEN estado='pendiente' AND vence_en<=:now THEN vence_en ELSE decidida_en END AS decidida_en
        FROM aari_visita_reprogramaciones WHERE coordinacion_id=:id ORDER BY creada_en DESC,id DESC'''),
        params).mappings().all()
    reports = session.execute(text('''SELECT id, fecha_visita, version_horario, autor_rol, tipo, observaciones,
            creada_en, autor_id=:user AS propio
        FROM aari_visita_ausencias WHERE coordinacion_id=:id ORDER BY creada_en DESC,id DESC'''),
        params).mappings().all()
    pending = next((item for item in proposals if item['estado'] == 'pendiente'), None)
    actions = []
    decisions = []
    if current and participant and _confirmed_visit(session, row):
        if now < row['propuesta_fecha']:
            if pending:
                actions.append(DECIDE)
                decisions = ['retirar'] if pending['propia'] else ['aceptar', 'rechazar']
            else:
                actions.append(PROPOSE)
        elif not any(report['propio'] and report['version_horario'] == row['version_horario'] for report in reports):
            actions.append(REPORT)
    return {
        'propuesta_pendiente': dict(pending) if pending else None,
        'decisiones': decisions,
        'reprogramaciones': [dict(item) for item in proposals if item['estado'] != 'pendiente'],
        'ausencias': [{key: value for key, value in report.items() if key != 'version_horario'} for report in reports],
    }, actions


def _confirmed_visit(session, row, *, lock=False):
    query = '''SELECT id FROM visitas WHERE id=:id AND reclamo_id=:claim AND proveedor_id=:provider
        AND estado='confirmada' AND fecha_confirmada=:day AND horario_confirmado=:time'''
    day = row['propuesta_fecha'].astimezone(ARGENTINA)
    return session.execute(text(query + (' FOR UPDATE' if lock else '')), {
        'id': row['visita_id'], 'claim': row['reclamo_id'], 'provider': row['proveedor_id'],
        'day': day.date(), 'time': day.strftime('%H:%M'),
    }).scalar_one_or_none()


def apply_followup(repo, session, row, source, user, action, payload, view):
    if not _confirmed_visit(session, row, lock=True):
        raise VisitError('La visita confirmada cambió. Actualizá antes de continuar.')
    now = repo._now(session)
    revision = row['version_horario']
    date = row['propuesta_fecha']
    params = {'id': row['id'], 'revision': revision, 'date': date, 'user': user.id, 'role': user.rol, 'now': now}
    if action == PROPOSE:
        valid_time(date, now)
        valid_time(payload.fecha, now)
        if payload.fecha == date:
            raise VisitError('Elegí un horario distinto del que ya está confirmado.', status=422)
        expire_proposal(session, row, now)
        deadline = min(now + timedelta(hours=24), date, payload.fecha)
        proposal_id = session.execute(text('''INSERT INTO aari_visita_reprogramaciones
            (coordinacion_id,version_horario,fecha_anterior,fecha_propuesta,solicitante_id,solicitante_rol,motivo,creada_en,vence_en)
            VALUES (:id,:revision,:date,:proposed,:user,:role,:note,:now,:deadline) RETURNING id'''),
            params | {'proposed': payload.fecha, 'note': payload.motivo, 'deadline': deadline}).scalar_one()
        recipient = row['proveedor_usuario_id'] if user.rol == 'inquilino' else row['inquilino_usuario_id']
        body = (f'Se propuso reprogramar la visita para el {visit_time(payload.fecha)} (Argentina). '
                f'La fecha vigente sigue siendo el {visit_time(date)} hasta que la contraparte acepte.')
        repo._notice(session, row, source, recipient, f'reprogramacion_propuesta:{proposal_id}', body)
        return body

    if action == REPORT:
        session.execute(text('''INSERT INTO aari_visita_ausencias
            (coordinacion_id,version_horario,fecha_visita,autor_id,autor_rol,tipo,observaciones,creada_en)
            VALUES (:id,:revision,:date,:user,:role,:kind,:note,:now)'''),
            params | {'kind': payload.tipo, 'note': payload.observaciones})
        return f'Se registró un reporte sobre la visita del {visit_time(date)} (Argentina).'

    pending = view['propuesta_pendiente']
    if now >= pending['vence_en'] or payload.propuesta_id != pending['id'] or payload.decision not in view['decisiones']:
        raise VisitError('La decisión debe corresponder a la propuesta vigente y al participante habilitado.')
    status = DECISIONS[payload.decision]
    session.execute(text('''UPDATE aari_visita_reprogramaciones SET estado=:status, decidida_en=:now,
            decision_usuario_id=:user, decision_rol=:role WHERE id=:proposal'''),
        params | {'proposal': pending['id'], 'status': status})
    if status != 'aceptada':
        return f'Propuesta {status}. La visita sigue confirmada para el {visit_time(date)} (Argentina).'

    new_date = pending['fecha_propuesta']
    local = new_date.astimezone(ARGENTINA)
    session.execute(text('''UPDATE visitas SET fecha_confirmada=:day, horario_confirmado=:time,
            recordatorio_24h_enviado=false, recordatorio_2h_enviado=false WHERE id=:visit'''),
        {'day': local.date(), 'time': local.strftime('%H:%M'), 'visit': row['visita_id']})
    session.execute(text('UPDATE reclamos SET fecha_visita=:date WHERE id=:claim'),
        {'date': new_date, 'claim': row['reclamo_id']})
    session.execute(text('''UPDATE aari_visita_coordinaciones SET propuesta_fecha=:date,
        propuesta_autor_id=:user, propuesta_version=version+1,
        version_horario=version_horario+1, actualizada_en=:now WHERE id=:id'''),
        params | {'date': new_date})
    session.execute(text('''UPDATE notificaciones n SET estado_envio='fallido',
        ultimo_error='Horario de visita reemplazado; aviso obsoleto.', proximo_intento_en=NULL,
        bloqueado_hasta=NULL, updated_at=clock_timestamp()
        FROM aari_visita_avisos a WHERE a.notificacion_id=n.id AND a.coordinacion_id=:id
        AND a.evento IN (:confirmed,:r24,:r2) AND n.estado_envio IN ('pendiente','procesando')'''), {
            'id': row['id'], 'confirmed': schedule_event('confirmada', revision),
            'r24': schedule_event('recordatorio_24', revision), 'r2': schedule_event('recordatorio_2', revision),
        })
    body = f'Visita reprogramada del {visit_time(date)} al {visit_time(new_date)} (Argentina).'
    for recipient in {row['inquilino_usuario_id'], row['proveedor_usuario_id'], row['responsable_usuario_id']}:
        repo._notice(session, row, source, recipient, schedule_event('confirmada', revision + 1), body)
    return body


def notice_matches_schedule(session, row, event, now):
    if row['etapa'] != 'confirmada' or now >= row['propuesta_fecha']:
        return False
    if event.startswith('reprogramacion_propuesta:'):
        return session.execute(text('''SELECT EXISTS(SELECT 1 FROM aari_visita_reprogramaciones
            WHERE coordinacion_id=:id AND id=CAST(:proposal AS uuid) AND estado='pendiente' AND vence_en>:now)'''),
            {'id': row['id'], 'proposal': event.split(':', 1)[1], 'now': now}).scalar_one()
    return event == schedule_event(event.split(':', 1)[0], row.get('version_horario', 0))
