"""HU33: avisos individuales y consultas técnicas explícitas, nunca un chat grupal."""

from sqlalchemy import bindparam, text

from app.db.quote_portal import SqlAlchemyQuotePortal
from app.services.conversations import ConversationError, EVENT_MESSAGES, budget_write_reason

CONTEXT_FROM = ''' FROM aari_solicitudes_presupuesto s
    JOIN aari_rondas_presupuesto rp ON rp.id=s.ronda_id
    JOIN reclamo_elecciones_proveedor ep ON ep.id=rp.eleccion_id
    JOIN reclamos r ON r.id=s.reclamo_id
    JOIN proveedores p ON p.id=s.proveedor_id
    JOIN inquilinos i ON i.id=r.inquilino_id
    JOIN propiedades prop ON prop.id=r.propiedad_id
    JOIN propietarios pr ON pr.id=prop.propietario_id
    LEFT JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
    LEFT JOIN presupuestos b ON b.solicitud_aari_id=s.id'''
CONTEXT = '''SELECT s.*,rp.eleccion_id,rp.contexto,rp.huella,rp.estado AS ronda_estado,rp.cerrada_en,
    ep.usuario_id AS original_actor,ep.actor_tipo AS original_role,rr.actor_tipo AS current_role,
    r.operador_asignado_id,r.numero,r.proveedor_seleccionado_id,r.presupuesto_seleccionado_id,
    p.usuario_id AS provider_user,p.activo AS provider_active,p.nombre_razon_social AS proveedor,
    i.usuario_id AS tenant_user,i.estado AS tenant_state,i.propiedad_id AS tenant_property,
    r.propiedad_id,pr.usuario_id AS owner_user,b.id AS presupuesto_id''' + CONTEXT_FROM + ' WHERE s.id=:id'


def _append(session, conversation, *, origin, name, body, actor=None, request=None, event=None, created=None):
    number = session.execute(text('''UPDATE aari_conversaciones SET ultimo_numero=ultimo_numero+1,
        actualizada_en=clock_timestamp() WHERE id=:id RETURNING ultimo_numero'''),
        {'id': conversation['id']}).scalar_one()
    return session.execute(text('''INSERT INTO aari_conversacion_mensajes
        (conversacion_id,numero,origen,autor_id,autor_nombre,texto,request_id,clave_evento,creado_en)
        VALUES (:id,:number,:origin,:actor,:name,:body,:request,:event,coalesce(:created,clock_timestamp()))
        RETURNING id,numero,origen,autor_id,autor_nombre,texto,creado_en'''),
        {'id': conversation['id'], 'number': number, 'origin': origin, 'actor': actor,
         'name': name, 'body': body, 'request': request, 'event': event, 'created': created}).mappings().one()


def _ensure(session, context):
    """Eventos separados para proveedor y responsable; no compartir el hilo económico."""
    for audience, participant in (('proveedor', context['usuario_id']), ('responsable', context['original_actor'])):
        session.execute(text('''INSERT INTO aari_conversaciones
            (solicitud_id,finalidad,audiencia,participante_usuario_id,responsable_usuario_id)
            VALUES (:id,'presupuesto',:audience,:user,:actor)
            ON CONFLICT(solicitud_id,finalidad,audiencia) DO NOTHING'''),
            {'id': context['id'], 'audience': audience, 'user': participant, 'actor': context['original_actor']})
    conversations = session.execute(text('''SELECT * FROM aari_conversaciones
        WHERE solicitud_id=:id AND finalidad='presupuesto' ORDER BY id FOR UPDATE'''),
        {'id': context['id']}).mappings().all()
    for conversation in conversations:
        events = session.execute(text('''SELECT e.id,e.tipo,e.creado_en FROM aari_presupuesto_eventos e
            WHERE e.ronda_id=:round AND (e.solicitud_id=:request OR e.solicitud_id IS NULL)
            AND NOT EXISTS (SELECT 1 FROM aari_conversacion_mensajes m
                WHERE m.conversacion_id=:conversation AND m.clave_evento='hu19:'||e.id::text)
            ORDER BY e.creado_en,e.id'''), {'round': context['ronda_id'], 'request': context['id'],
                'conversation': conversation['id']}).mappings().all()
        for event in events:
            if event['tipo'] in EVENT_MESSAGES:
                _append(session, conversation, origin='agente', name='Agente AARI',
                        body=EVENT_MESSAGES[event['tipo']], event='hu19:' + str(event['id']), created=event['creado_en'])


def sync_round_events(session, round_id, *, request_id=None):
    scope = ' AND id=:request' if request_id is not None else ''
    ids = session.execute(text('SELECT id FROM aari_solicitudes_presupuesto WHERE ronda_id=:id' + scope + ' ORDER BY id'),
                          {'id': round_id, 'request': request_id}).scalars().all()
    for rid in ids:
        _ensure(session, session.execute(text(CONTEXT), {'id': rid}).mappings().one())


def unread_counts(session, request_ids, user_id):
    if not request_ids:
        return {}
    rows = session.execute(text('''SELECT c.solicitud_id,count(m.id) AS unread FROM aari_conversaciones c
        JOIN aari_solicitudes_presupuesto s ON s.id=c.solicitud_id
        LEFT JOIN aari_conversacion_lecturas l ON l.conversacion_id=c.id AND l.usuario_id=:user
        LEFT JOIN aari_conversacion_mensajes m ON m.conversacion_id=c.id
            AND m.numero>coalesce(l.ultimo_numero,0) AND m.autor_id IS DISTINCT FROM :user
        WHERE c.solicitud_id IN :ids AND (c.participante_usuario_id=:user
            OR (c.finalidad='consulta_tecnica' AND s.usuario_id=:user))
        GROUP BY c.solicitud_id''').bindparams(bindparam('ids', expanding=True)),
        {'ids': request_ids, 'user': user_id}).mappings().all()
    return {row['solicitud_id']: row['unread'] for row in rows}


def _missing():
    return ConversationError('No encontramos esa conversación.', status=404, code='conversation_not_found')


class SqlAlchemyConversations(SqlAlchemyQuotePortal):
    def _account(self, session, user):
        row = session.execute(text('''SELECT id,rol::text AS rol,activo,primer_ingreso,nombre_completo
            FROM usuarios WHERE id=:id FOR SHARE'''), {'id': user.id}).mappings().one_or_none()
        if not row or not row['activo'] or row['primer_ingreso'] or row['rol'] != user.rol:
            raise _missing()
        return row

    def _context(self, session, request_id, user):
        claim = session.execute(text('SELECT reclamo_id FROM aari_solicitudes_presupuesto WHERE id=:id'),
                                {'id': request_id}).scalar_one_or_none()
        if claim is None:
            raise _missing()
        session.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id': claim})
        context = session.execute(text(CONTEXT + ' FOR SHARE OF s,rp,ep,p,i,prop,pr'),
                                  {'id': request_id}).mappings().one()
        account = self._account(session, user)
        provider = (user.rol == 'proveedor' and user.perfil_id == context['proveedor_id']
                    and user.id == context['usuario_id'] == context['provider_user'] and context['provider_active'])
        tenant = (user.rol == 'inquilino' and user.id == context['tenant_user']
                  and context['tenant_state'] == 'activo' and context['tenant_property'] == context['propiedad_id'])
        owner = user.rol == 'propietario' and user.id == context['owner_user']
        responsible = ((tenant or owner) and user.id == context['original_actor']
                       and user.rol == context['original_role'] == context['current_role'])
        agency = user.rol == 'administrador' or (user.rol == 'operador' and user.id == context['operador_asignado_id'])
        if not (provider or tenant or responsible or agency):
            raise _missing()
        return context, account, {'provider': provider, 'tenant': tenant, 'responsible': responsible, 'agency': agency}

    def _authorized(self, session, request_id, user, thread_id=None):
        context, account, roles = self._context(session, request_id, user)
        _ensure(session, context)
        if thread_id:
            thread = session.execute(text('''SELECT * FROM aari_conversaciones
                WHERE id=:thread AND solicitud_id=:request FOR UPDATE'''),
                {'thread': thread_id, 'request': request_id}).mappings().one_or_none()
        else:
            audience = 'proveedor' if roles['provider'] or roles['agency'] else 'responsable'
            thread = session.execute(text('''SELECT * FROM aari_conversaciones
                WHERE solicitud_id=:id AND finalidad='presupuesto' AND audiencia=:audience FOR UPDATE'''),
                {'id': request_id, 'audience': audience}).mappings().one_or_none()
        if not thread or thread['finalidad'] == 'coordinacion':
            raise _missing()
        if thread['finalidad'] == 'presupuesto':
            allowed = roles['agency'] or (thread['participante_usuario_id'] == user.id
                       and (roles['provider'] if thread['audiencia'] == 'proveedor' else roles['responsible']))
        else:
            allowed = roles['agency'] or roles['provider'] or (roles['tenant'] and thread['participante_usuario_id'] == user.id)
        if not allowed:
            raise _missing()
        return context, account, roles, thread

    def _technical_reason(self, session, context):
        reason = budget_write_reason(context, session.execute(text('SELECT clock_timestamp()')).scalar_one(),
                                     current=self._current(session, context))
        if reason:
            return reason
        if context['presupuesto_id']:
            return 'El presupuesto ya fue presentado. Las consultas técnicas quedaron cerradas.'
        return None

    def _reason(self, session, context, roles, thread):
        if roles['agency']:
            return 'La inmobiliaria consulta el historial. No participa escribiendo en el recorrido normal.'
        if thread['finalidad'] != 'consulta_tecnica':
            return 'Son avisos del agente. Las decisiones se confirman mediante las acciones de cada etapa.'
        if thread['consultas_cerradas_en'] is not None:
            return 'Las consultas finalizaron. El historial se conserva en sólo lectura.'
        reason = self._technical_reason(session, context)
        if reason:
            return reason
        tenant = session.execute(text('''SELECT id FROM usuarios WHERE id=:id AND rol='inquilino'
            AND activo AND NOT primer_ingreso FOR SHARE'''), {'id': thread['participante_usuario_id']}).scalar_one_or_none()
        if (not tenant or tenant != context['tenant_user'] or context['tenant_state'] != 'activo'
                or context['tenant_property'] != context['propiedad_id']):
            return 'El inquilino ya no tiene acceso activo a esta consulta.'
        return None

    @staticmethod
    def _reader(session, conversation, user_id, *, audit=False):
        last = session.execute(text('''SELECT ultimo_numero FROM aari_conversacion_lecturas
            WHERE conversacion_id=:id AND usuario_id=:user'''),
            {'id': conversation['id'], 'user': user_id}).scalar_one_or_none() or 0
        unread = 0 if audit else session.execute(text('''SELECT count(*) FROM aari_conversacion_mensajes
            WHERE conversacion_id=:id AND numero>:last AND autor_id IS DISTINCT FROM :user'''),
            {'id': conversation['id'], 'last': last, 'user': user_id}).scalar_one()
        return last, unread

    @staticmethod
    def _message(row, user_id):
        return {key: row[key] for key in ('id', 'numero', 'origen', 'autor_nombre', 'texto', 'creado_en')} | {'propio': row['autor_id'] == user_id}

    def messages(self, request_id, user, *, before=None, after=None, limit=30, thread_id=None):
        if before is not None and after is not None:
            raise ConversationError('Usá un solo sentido de paginación.', status=422, code='invalid_cursor')
        with self.transaction() as session:
            context, _, roles, thread = self._authorized(session, request_id, user, thread_id)
            direction = 'ASC' if after is not None else 'DESC'
            bound = ' AND numero>:cursor' if after is not None else ' AND numero<:cursor' if before is not None else ''
            rows = session.execute(text('''SELECT id,numero,origen,autor_id,autor_nombre,texto,creado_en
                FROM aari_conversacion_mensajes WHERE conversacion_id=:id''' + bound +
                ' ORDER BY numero ' + direction + ' LIMIT :limit'),
                {'id': thread['id'], 'cursor': after if after is not None else before, 'limit': limit + 1}).mappings().all()
            more, rows = len(rows) > limit, rows[:limit]
            if after is None:
                rows = rows[::-1]
            read, unread = self._reader(session, thread, user.id, audit=roles['agency'])
            reason = self._reason(session, context, roles, thread)
            return {'id': thread['id'], 'solicitud_id': request_id, 'finalidad': thread['finalidad'],
                    'numero_reclamo': context['numero'], 'puede_enviar': reason is None, 'motivo_solo_lectura': reason,
                    'puede_finalizar': roles['provider'] and reason is None,
                    'ultimo_numero': thread['ultimo_numero'], 'leido_hasta': read, 'no_leidos': unread,
                    'hay_anteriores': more if after is None else False, 'hay_nuevos': more if after is not None else False,
                    'items': [self._message(row, user.id) for row in rows]}

    def _request_for_thread(self, thread_id):
        with self.transaction() as session:
            rid = session.execute(text('SELECT solicitud_id FROM aari_conversaciones WHERE id=:id'),
                                  {'id': thread_id}).scalar_one_or_none()
            if rid is None:
                raise _missing()
            return rid

    def thread_messages(self, thread_id, user, **kwargs):
        return self.messages(self._request_for_thread(thread_id), user, thread_id=thread_id, **kwargs)

    def send(self, request_id, user, payload, *, thread_id=None):
        with self.transaction() as session:
            context, account, roles, thread = self._authorized(session, request_id, user, thread_id)
            if thread['finalidad'] != 'consulta_tecnica' or roles['agency']:
                raise ConversationError('Este hilo no admite mensajes directos.', status=403, code='thread_read_only')
            existing = session.execute(text('''SELECT * FROM aari_conversacion_mensajes
                WHERE conversacion_id=:id AND autor_id=:user AND request_id=:key'''),
                {'id': thread['id'], 'user': user.id, 'key': payload.request_id}).mappings().one_or_none()
            if existing:
                if existing['texto'] != payload.texto:
                    raise ConversationError('Este envío ya fue usado para otro mensaje.', code='message_key_reused')
                return {'mensaje': self._message(existing, user.id), 'repetido': True}
            reason = self._reason(session, context, roles, thread)
            if reason:
                raise ConversationError(reason, code='conversation_read_only')
            name = account['nombre_completo'] or ('Proveedor' if roles['provider'] else 'Inquilino')
            row = _append(session, thread, origin='humano', name=name, body=payload.texto, actor=user.id, request=payload.request_id)
            return {'mensaje': self._message(row, user.id), 'repetido': False}

    def thread_send(self, thread_id, user, payload):
        return self.send(self._request_for_thread(thread_id), user, payload, thread_id=thread_id)

    def mark_read(self, request_id, user, through, *, thread_id=None):
        with self.transaction() as session:
            _, _, roles, thread = self._authorized(session, request_id, user, thread_id)
            if through > thread['ultimo_numero']:
                raise ConversationError('No se pueden marcar mensajes futuros como leídos.', status=422, code='invalid_read_position')
            last = session.execute(text('''INSERT INTO aari_conversacion_lecturas
                (conversacion_id,usuario_id,ultimo_numero) VALUES (:id,:user,:through)
                ON CONFLICT(conversacion_id,usuario_id) DO UPDATE SET
                ultimo_numero=greatest(aari_conversacion_lecturas.ultimo_numero,excluded.ultimo_numero)
                RETURNING ultimo_numero'''), {'id': thread['id'], 'user': user.id, 'through': through}).scalar_one()
            return {'leido_hasta': last, 'no_leidos': self._reader(session, thread, user.id, audit=roles['agency'])[1]}

    def thread_read(self, thread_id, user, through):
        return self.mark_read(self._request_for_thread(thread_id), user, through, thread_id=thread_id)

    def open_questions(self, request_id, user, payload):
        with self.transaction() as session:
            context, _, roles = self._context(session, request_id, user)
            if not roles['provider']:
                raise ConversationError('Sólo el proveedor puede iniciar las consultas.', status=403, code='provider_required')
            existing = session.execute(text('''SELECT * FROM aari_conversaciones WHERE solicitud_id=:id
                AND finalidad='consulta_tecnica' FOR UPDATE'''), {'id': request_id}).mappings().one_or_none()
            if existing:
                if existing['participante_usuario_id'] != context['tenant_user']:
                    raise _missing()
                if existing['consultas_cerradas_en'] and existing['apertura_request_id'] != payload.request_id:
                    raise ConversationError('Las consultas ya finalizaron. Continuá con el presupuesto.', code='questions_finished')
                return {'id': existing['id'], 'repetido': True}
            tenant = session.execute(text('''SELECT id FROM usuarios WHERE id=:id AND rol='inquilino'
                AND activo AND NOT primer_ingreso FOR SHARE'''), {'id': context['tenant_user']}).scalar_one_or_none()
            if not tenant or context['tenant_state'] != 'activo' or context['tenant_property'] != context['propiedad_id']:
                raise ConversationError('El inquilino necesita acceso activo a AARI para recibir las consultas.', code='tenant_unavailable')
            reason = self._technical_reason(session, context)
            if reason:
                raise ConversationError(reason, code='conversation_read_only')
            _ensure(session, context)
            thread = session.execute(text('''INSERT INTO aari_conversaciones
                (solicitud_id,finalidad,audiencia,participante_usuario_id,responsable_usuario_id,
                 apertura_request_id,consultas_abiertas_en)
                VALUES (:id,'consulta_tecnica','inquilino',:tenant,:actor,:key,clock_timestamp()) RETURNING *'''),
                {'id': request_id, 'tenant': tenant, 'actor': context['original_actor'], 'key': payload.request_id}).mappings().one()
            _append(session, thread, origin='agente', name='Agente AARI', event='consulta:apertura',
                    body='El proveedor necesita aclaraciones técnicas del inquilino antes de presupuestar. Las consultas no amplían el plazo de la solicitud.')
            return {'id': thread['id'], 'repetido': False}

    def finish_questions(self, thread_id, user, payload):
        rid = self._request_for_thread(thread_id)
        with self.transaction() as session:
            context, _, roles, thread = self._authorized(session, rid, user, thread_id)
            if not roles['provider'] or thread['finalidad'] != 'consulta_tecnica':
                raise ConversationError('Sólo el proveedor puede finalizar estas consultas.', status=403, code='provider_required')
            if thread['consultas_cerradas_en']:
                return {'id': thread['id'], 'repetido': True}
            reason = self._technical_reason(session, context)
            if reason:
                raise ConversationError(reason, code='conversation_read_only')
            session.execute(text('''UPDATE aari_conversaciones SET consultas_cerradas_en=clock_timestamp(),
                cierre_request_id=:key WHERE id=:id'''), {'id': thread_id, 'key': payload.request_id})
            _append(session, thread, origin='agente', name='Agente AARI', event='consulta:cierre',
                    body='El proveedor finalizó las consultas. El historial queda en sólo lectura; el presupuesto se envía mediante su formulario.')
            return {'id': thread_id, 'repetido': False}

    def _bootstrap_inbox(self, session, user):
        # Proyección en lote: no hace una consulta de mensajes por cada tarjeta.
        if user.rol not in {'proveedor', 'inquilino', 'propietario'}:
            return
        # Mismo orden que HU19: reclamo antes del hilo. Sólo bloquear lo que
        # necesita recuperación, no todas las conversaciones en cada sondeo.
        types = ','.join("'" + kind + "'" for kind in EVENT_MESSAGES)
        claims = session.execute(text('''SELECT r.id FROM reclamos r WHERE EXISTS (
            SELECT 1 FROM aari_solicitudes_presupuesto s
            JOIN aari_rondas_presupuesto rp ON rp.id=s.ronda_id
            JOIN reclamo_elecciones_proveedor ep ON ep.id=rp.eleccion_id
            WHERE s.reclamo_id=r.id AND (s.usuario_id=:user OR ep.usuario_id=:user)
            AND (NOT EXISTS(SELECT 1 FROM aari_conversaciones c WHERE c.solicitud_id=s.id
                AND c.finalidad='presupuesto' AND c.participante_usuario_id=:user)
            OR EXISTS(SELECT 1 FROM aari_presupuesto_eventos e WHERE e.ronda_id=s.ronda_id
                AND (e.solicitud_id=s.id OR e.solicitud_id IS NULL) AND e.tipo IN (''' + types + ''')
                AND NOT EXISTS(SELECT 1 FROM aari_conversaciones c
                    JOIN aari_conversacion_mensajes m ON m.conversacion_id=c.id
                    WHERE c.solicitud_id=s.id AND c.finalidad='presupuesto'
                    AND c.participante_usuario_id=:user AND m.clave_evento='hu19:'||e.id::text))))
            ORDER BY r.id FOR UPDATE'''), {'user': user.id}).scalars().all()
        if not claims:
            return
        scope = {'user': user.id, 'claims': claims}
        session.execute(text('''INSERT INTO aari_conversaciones
            (solicitud_id,finalidad,audiencia,participante_usuario_id,responsable_usuario_id)
            SELECT s.id,'presupuesto',CASE WHEN s.usuario_id=:user THEN 'proveedor' ELSE 'responsable' END,
                :user,ep.usuario_id FROM aari_solicitudes_presupuesto s
            JOIN aari_rondas_presupuesto rp ON rp.id=s.ronda_id
            JOIN reclamo_elecciones_proveedor ep ON ep.id=rp.eleccion_id
            WHERE (s.usuario_id=:user OR ep.usuario_id=:user) AND s.reclamo_id IN :claims
            ON CONFLICT(solicitud_id,finalidad,audiencia) DO NOTHING''').bindparams(bindparam('claims', expanding=True)), scope)
        session.execute(text('''SELECT c.id FROM aari_conversaciones c
            JOIN aari_solicitudes_presupuesto s ON s.id=c.solicitud_id WHERE c.finalidad='presupuesto'
            AND c.participante_usuario_id=:user AND s.reclamo_id IN :claims ORDER BY c.id FOR UPDATE OF c''')
            .bindparams(bindparam('claims', expanding=True)), scope).all()
        params = {**scope, **{'event_' + str(n): body for n, body in enumerate(EVENT_MESSAGES.values())}}
        cases = ' '.join("WHEN '" + kind + "' THEN :event_" + str(n) for n, kind in enumerate(EVENT_MESSAGES))
        session.execute(text('''WITH pending AS (SELECT c.id AS conversation,e.id AS event,e.creado_en,
            c.ultimo_numero+row_number() OVER(PARTITION BY c.id ORDER BY e.creado_en,e.id) AS number,
            CASE e.tipo ''' + cases + ''' END AS body FROM aari_conversaciones c
            JOIN aari_solicitudes_presupuesto s ON s.id=c.solicitud_id
            JOIN aari_presupuesto_eventos e ON e.ronda_id=s.ronda_id AND (e.solicitud_id=s.id OR e.solicitud_id IS NULL)
            WHERE c.finalidad='presupuesto' AND c.participante_usuario_id=:user
            AND s.reclamo_id IN :claims AND e.tipo IN (''' + types + ''')
            AND NOT EXISTS(SELECT 1 FROM aari_conversacion_mensajes m WHERE m.conversacion_id=c.id
                AND m.clave_evento='hu19:'||e.id::text)), inserted AS (
            INSERT INTO aari_conversacion_mensajes(conversacion_id,numero,origen,autor_nombre,texto,clave_evento,creado_en)
            SELECT conversation,number,'agente','Agente AARI',body,'hu19:'||event::text,creado_en FROM pending
            RETURNING conversacion_id,numero)
            UPDATE aari_conversaciones c SET ultimo_numero=x.last,actualizada_en=clock_timestamp()
            FROM(SELECT conversacion_id,max(numero) AS last FROM inserted GROUP BY conversacion_id) x
            WHERE c.id=x.conversacion_id''').bindparams(bindparam('claims', expanding=True)), params)

    def inbox(self, user, *, page=1, page_size=20):
        with self.transaction() as session:
            self._account(session, user)
            self._bootstrap_inbox(session, user)
            provider = '''s.usuario_id=:user AND p.usuario_id=:user AND p.id=:profile AND p.activo AND
                ((c.finalidad='presupuesto' AND c.audiencia='proveedor' AND c.participante_usuario_id=:user)
                 OR c.finalidad='consulta_tecnica')'''
            tenant = '''i.usuario_id=:user AND i.estado='activo' AND i.propiedad_id=r.propiedad_id AND
                c.participante_usuario_id=:user AND (c.finalidad='consulta_tecnica' OR
                (c.audiencia='responsable' AND ep.usuario_id=:user AND ep.actor_tipo='inquilino' AND rr.actor_tipo='inquilino'))'''
            owner = '''pr.usuario_id=:user AND ep.usuario_id=:user AND c.participante_usuario_id=:user
                AND c.finalidad='presupuesto' AND c.audiencia='responsable'
                AND ep.actor_tipo='propietario' AND rr.actor_tipo='propietario' '''
            scope = {'proveedor': provider, 'inquilino': tenant, 'propietario': owner,
                     'administrador': 'true', 'operador': 'r.operador_asignado_id=:user'}.get(user.rol, 'false')
            audit = user.rol in {'administrador', 'operador'}
            source = CONTEXT_FROM + ''' JOIN aari_conversaciones c ON c.solicitud_id=s.id
                LEFT JOIN aari_conversacion_lecturas l ON l.conversacion_id=c.id AND l.usuario_id=:user
                LEFT JOIN LATERAL(SELECT count(*) AS unread FROM aari_conversacion_mensajes m
                    WHERE m.conversacion_id=c.id AND m.numero>coalesce(l.ultimo_numero,0)
                    AND m.autor_id IS DISTINCT FROM :user) unread ON true
                WHERE c.finalidad IN ('presupuesto','consulta_tecnica') AND (''' + scope + ')'
            params = {'user': user.id, 'profile': user.perfil_id, 'audit': audit, 'limit': page_size}
            stats = session.execute(text('SELECT count(*) AS total,coalesce(sum(CASE WHEN :audit THEN 0 ELSE unread.unread END),0) AS unread' + source), params).mappings().one()
            last_page = max(1, (stats['total'] + page_size - 1) // page_size)
            page = min(page, last_page)
            rows = session.execute(text('''SELECT c.id,c.solicitud_id,c.finalidad,c.audiencia,r.numero,
                p.nombre_razon_social AS proveedor,c.actualizada_en,c.consultas_cerradas_en,
                CASE WHEN :audit THEN 0 ELSE unread.unread END AS no_leidos''' + source +
                ' ORDER BY c.actualizada_en DESC,c.id DESC LIMIT :limit OFFSET :offset'),
                {**params, 'offset': (page - 1) * page_size}).mappings().all()
            return {'items': [dict(row) for row in rows], 'total': stats['total'], 'no_leidos': stats['unread'],
                    'page': page, 'page_size': page_size}
