"""HU23: decisiones transaccionales; nunca selecciona un presupuesto ni envía SMTP."""
from datetime import timedelta
import hashlib
import json
from uuid import uuid4

from sqlalchemy import text

from app.agents.coordination.visits import visit_graph
from app.db.quote_requests import SqlAlchemyQuoteRequests
from app.db.visit_followups import (
    FOLLOWUP_ACTIONS, apply_followup, expire_proposal, notice_matches_schedule,
    read_followup, schedule_event,
)
from app.services.visits import ARGENTINA, VisitError, WAITING, reminder_due, valid_time, validate_options


SOURCE = '''SELECT r.id,r.numero,r.estado,r.updated_at,r.fecha_visita,r.tipo_gasto::text,
    r.propiedad_id,r.inquilino_id,r.proveedor_seleccionado_id,r.presupuesto_seleccionado_id,
    r.operador_asignado_id,p.propietario_id,p.direccion,p.localidad,p.provincia,
    i.usuario_id AS tenant_user,i.estado AS tenant_state,i.propiedad_id AS tenant_property,
    b.id AS budget,b.proveedor_id,b.solicitud_aari_id AS solicitud_id,b.monto,b.moneda,b.tipo_importe,
    s.usuario_id AS request_provider_user,pr.usuario_id AS provider_user,pr.activo AS provider_active,
    pr.nombre_razon_social AS proveedor,ep.usuario_id AS actor_user,ep.actor_tipo,
    rr.actor_tipo AS current_actor,owner.usuario_id AS owner_user,
    tu.activo AND NOT tu.primer_ingreso AND tu.rol='inquilino' AS tenant_active,
    pu.activo AND NOT pu.primer_ingreso AND pu.rol='proveedor' AS provider_active_account,
    au.activo AND NOT au.primer_ingreso AND au.rol::text=ep.actor_tipo AS actor_active,
    a.decision AS autorizacion,rp.eleccion_id,rp.huella AS ronda_huella,
    sp.id AS seleccion_id,sp.decidido_en AS seleccion_decidida_en,
    (sp.usuario_id=ep.usuario_id AND sp.monto=b.monto AND sp.monto=r.monto_seleccionado
        AND sp.moneda=b.moneda AND sp.tipo_importe=b.tipo_importe
        AND sp.modalidad='fidelizado') AS seleccion_consistente
    FROM reclamos r JOIN propiedades p ON p.id=r.propiedad_id
    JOIN inquilinos i ON i.id=r.inquilino_id JOIN propietarios owner ON owner.id=p.propietario_id
    JOIN presupuestos b ON b.id=r.presupuesto_seleccionado_id AND b.reclamo_id=r.id
        AND b.proveedor_id=r.proveedor_seleccionado_id
    JOIN aari_solicitudes_presupuesto s ON s.id=b.solicitud_aari_id AND s.reclamo_id=r.id AND s.proveedor_id=b.proveedor_id
    JOIN aari_rondas_presupuesto rp ON rp.id=s.ronda_id
    JOIN reclamo_elecciones_proveedor ep ON ep.id=rp.eleccion_id
    JOIN reclamo_selecciones_presupuesto sp ON sp.reclamo_id=r.id
        AND sp.eleccion_id=ep.id AND sp.ronda_id=rp.id
        AND sp.presupuesto_id=b.id AND sp.proveedor_id=b.proveedor_id
    JOIN reclamo_responsables rr ON rr.reclamo_id=r.id AND rr.solicitado_en=ep.solicitud_responsable_en
    JOIN proveedores pr ON pr.id=b.proveedor_id
    LEFT JOIN usuarios tu ON tu.id=i.usuario_id LEFT JOIN usuarios pu ON pu.id=pr.usuario_id
    LEFT JOIN usuarios au ON au.id=ep.usuario_id
    LEFT JOIN reclamo_autorizaciones a ON a.reclamo_id=r.id AND a.solicitado_en=rr.solicitado_en
        AND a.usuario_id=ep.usuario_id WHERE r.id=:id'''
CONTEXT_KEYS = ('propiedad_id','inquilino_id','propietario_id','tenant_user','provider_user','actor_user',
                'actor_tipo','current_actor','owner_user','direccion','localidad','provincia','budget',
                'proveedor_id','solicitud_id','eleccion_id','ronda_huella','monto','moneda','tipo_importe',
                'seleccion_id','seleccion_decidida_en')


def _context(source):
    return {key: str(source[key]) if source[key] is not None else None for key in CONTEXT_KEYS}


def _eligible(source):
    return bool(source and source['estado'] in {'Proveedor seleccionado', 'Visita programada'}
        and source['seleccion_consistente']
        and source['tenant_active'] and source['provider_active_account'] and source['actor_active']
        and source['provider_active'] and source['provider_user'] == source['request_provider_user']
        and source['tenant_state'] == 'activo' and source['tenant_property'] == source['propiedad_id']
        and source['actor_tipo'] == source['current_actor']
        and ((source['tipo_gasto'] == 'ordinario' and source['actor_tipo'] == 'inquilino'
              and source['actor_user'] == source['tenant_user'])
             or (source['tipo_gasto'] == 'extraordinario' and source['actor_tipo'] == 'propietario'
                 and source['actor_user'] == source['owner_user'] and source['autorizacion'] == 'autorizar')))


def available(session):
    return getattr(session, 'bind', session).dialect.name == 'postgresql' and session.execute(text(
        """SELECT to_regclass('public.reclamo_selecciones_presupuesto') IS NOT NULL
            AND EXISTS(SELECT 1 FROM pg_attribute
                WHERE attrelid=to_regclass('public.aari_visita_coordinaciones')
                AND attname='seleccion_id' AND NOT attisdropped)""")).scalar_one()


class SqlAlchemyVisits(SqlAlchemyQuoteRequests):
    def list_own(self, user, *, page=1, page_size=20):
        with self.transaction() as session:
            account=session.execute(text('SELECT rol::text FROM usuarios WHERE id=:id AND activo AND NOT primer_ingreso'), {'id':user.id}).scalar_one_or_none()
            if account!=user.rol: raise VisitError('La cuenta no está habilitada.',status=403)
            scopes={
                'inquilino':"v.inquilino_usuario_id=:user AND i.usuario_id=:user AND i.id=:profile AND i.estado='activo' AND i.propiedad_id=r.propiedad_id",
                'proveedor':"v.proveedor_usuario_id=:user AND pr.usuario_id=:user AND pr.id=:profile AND pr.activo",
                'propietario':"v.responsable_usuario_id=:user AND owner.usuario_id=:user",
                'administrador':'true','operador':'r.operador_asignado_id=:user',
            }
            source=''' FROM aari_visita_coordinaciones v JOIN reclamos r ON r.id=v.reclamo_id
                JOIN inquilinos i ON i.id=v.inquilino_id JOIN propiedades p ON p.id=r.propiedad_id
                JOIN propietarios owner ON owner.id=p.propietario_id JOIN proveedores pr ON pr.id=v.proveedor_id
                WHERE v.seleccion_id IS NOT NULL
                AND v.presupuesto_id=r.presupuesto_seleccionado_id AND v.proveedor_id=r.proveedor_seleccionado_id
                AND v.id=(SELECT x.id FROM aari_visita_coordinaciones x WHERE x.reclamo_id=r.id ORDER BY x.creada_en DESC,x.id DESC LIMIT 1)
                AND ('''+scopes.get(user.rol,'false')+')'
            params={'user':user.id,'profile':user.perfil_id}
            total=session.execute(text('SELECT count(*)'+source),params).scalar_one()
            page=min(page,max(1,(total+page_size-1)//page_size))
            rows=session.execute(text('SELECT v.id,v.reclamo_id,r.numero,v.etapa,v.vence_en,v.propuesta_fecha AS fecha_confirmada,pr.nombre_razon_social AS proveedor'+source+
                ' ORDER BY v.actualizada_en DESC,v.id DESC LIMIT :limit OFFSET :offset'),{**params,'limit':page_size,'offset':(page-1)*page_size}).mappings().all()
            return {'items':[dict(row) for row in rows],'page':page,'page_size':page_size,'total':total}

    @staticmethod
    def _source(session, claim):
        source=session.execute(text(SOURCE+' FOR SHARE OF p,i,owner,b,s,rp,ep,rr,pr,sp'), {'id': claim}).mappings().one_or_none()
        if source:
            session.execute(text('SELECT id FROM usuarios WHERE id IN (:tenant,:provider,:actor) ORDER BY id FOR SHARE'),
                {'tenant':source['tenant_user'],'provider':source['provider_user'],'actor':source['actor_user']}).all()
            # Releer los flags después de adquirir las reservas de participantes.
            source=session.execute(text(SOURCE), {'id':claim}).mappings().one_or_none()
        return source

    @staticmethod
    def _now(session):
        return session.execute(text('SELECT clock_timestamp()')).scalar_one()

    @staticmethod
    def _current(row, source):
        if (not _eligible(source) or row['seleccion_id'] != source['seleccion_id']
                or row['contexto'] != _context(source)):
            return False
        if row['etapa'] == 'confirmada':
            return source['estado'] == 'Visita programada' and source['fecha_visita'] == row['propuesta_fecha']
        return source['estado'] == 'Proveedor seleccionado' and source['updated_at'] == row['seleccion_version']

    @staticmethod
    def _row(session, claim):
        return session.execute(text('''SELECT * FROM aari_visita_coordinaciones WHERE reclamo_id=:id
            ORDER BY creada_en DESC,id DESC LIMIT 1 FOR UPDATE'''), {'id': claim}).mappings().one_or_none()

    def _scope(self, session, claim, user):
        # Orden compatible con HU19/HU33: reclamo antes de coordinación/hilo.
        if not session.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id': claim}).scalar_one_or_none():
            raise VisitError('No encontramos esta coordinación.', status=404)
        account = session.execute(text('''SELECT id,rol::text AS rol,nombre_completo FROM usuarios
            WHERE id=:id AND activo AND NOT primer_ingreso FOR SHARE'''), {'id': user.id}).mappings().one_or_none()
        if not account or account['rol'] != user.rol:
            raise VisitError('La cuenta no está habilitada.', status=403)
        row, source = self._row(session, claim), self._source(session, claim)
        if not row or not source:
            raise VisitError('La coordinación todavía no está disponible.', status=404)
        tenant = (user.rol == 'inquilino' and user.id == row['inquilino_usuario_id'] == source['tenant_user']
                  and user.perfil_id == row['inquilino_id'] and source['tenant_state'] == 'activo'
                  and source['tenant_property'] == source['propiedad_id'])
        provider = (user.rol == 'proveedor' and user.id == row['proveedor_usuario_id'] == source['provider_user']
                    and user.perfil_id == row['proveedor_id'] and source['provider_active'])
        responsible = user.id == row['responsable_usuario_id'] == source['actor_user'] and (
            tenant or user.rol == 'propietario' and user.id == source['owner_user'])
        agency = user.rol == 'administrador' or user.rol == 'operador' and user.id == source['operador_asignado_id']
        if not (tenant or provider or responsible or agency):
            raise VisitError('No encontramos esta coordinación.', status=404)
        return row, source, account, {'tenant': tenant, 'provider': provider, 'responsible': responsible, 'agency': agency}

    def _info(self, session, row, source, user, roles):
        now = self._now(session)
        current = self._current(row, source)
        expired = row['etapa'] in WAITING and row['vence_en'] is not None and now >= row['vence_en']
        writable = current and not expired
        actions = []
        if writable:
            if roles['tenant'] and row['etapa'] == 'esperando_disponibilidad': actions = ['disponibilidad']
            if roles['provider'] and row['etapa'] == 'esperando_confirmacion': actions = ['confirmar', 'sin-coincidencia']
            if (roles['tenant'] or roles['provider']) and row['etapa'] == 'negociando':
                actions = ['proponer']
                if row['propuesta_fecha'] and row['propuesta_autor_id'] != user.id and row['propuesta_fecha'] > now:
                    actions.append('confirmar')
        thread = session.execute(text('''SELECT id FROM aari_conversaciones WHERE coordinacion_visita_id=:id
            AND audiencia=:audience'''), {'id':row['id'], 'audience':'inquilino' if roles['tenant'] or roles['provider'] or roles['agency'] else 'responsable'}).scalar_one_or_none()
        followup, followup_actions = read_followup(session, row, user, roles, now, current)
        actions.extend(followup_actions)
        participant = roles['tenant'] or roles['provider']
        can_chat = writable and participant and (row['etapa'] == 'negociando' or (
            row['etapa'] == 'confirmada' and followup is not None))
        return {'id':row['id'],'reclamo_id':row['reclamo_id'],'numero':source['numero'],
            'etapa':row['etapa'],'version':row['version'],'proveedor':source['proveedor'],
            'urgencia':session.execute(text('SELECT urgencia::text FROM reclamos WHERE id=:id'), {'id':row['reclamo_id']}).scalar_one(),
            'ubicacion':' · '.join(str(source[k]) for k in ('direccion','localidad','provincia')),
            'vence_en':row['vence_en'],'fecha_confirmada':row['propuesta_fecha'] if row['etapa']=='confirmada' else None,
            'propuesta':({'fecha':row['propuesta_fecha'],'version':row['propuesta_version'],
                         'propia':row['propuesta_autor_id']==user.id} if row['propuesta_fecha'] else None),
            'opciones':[dict(v) for v in session.execute(text('SELECT id,desde,hasta FROM aari_visita_opciones WHERE coordinacion_id=:id ORDER BY desde,id'), {'id':row['id']}).mappings().all()],
            'acciones':actions,'vigente':current,'vencida':expired,'hilo_id':thread,
            'puede_conversar':can_chat, 'seguimiento':followup,
            'motivo_solo_lectura':None if actions else ('La coordinación cambió; no admite nuevas acciones.' if not current else
                'Finalizó el plazo para acordar la visita.' if expired and row['etapa']!='confirmada' else
                'Podés consultar la coordinación; la acción corresponde al otro participante o la etapa ya finalizó.')}

    def get(self, claim, user):
        with self.transaction() as session:
            row, source, _, roles = self._scope(session, claim, user)
            return self._info(session, row, source, user, roles)

    def _event(self, session, row, body, key, *, participants_only=False):
        from app.db.conversations import _append
        threads = session.execute(text('''SELECT * FROM aari_conversaciones WHERE coordinacion_visita_id=:id
            AND (NOT :restricted OR audiencia='inquilino') ORDER BY id FOR UPDATE'''),
            {'id':row['id'], 'restricted':participants_only}).mappings().all()
        for thread in threads:
            if not session.execute(text('SELECT id FROM aari_conversacion_mensajes WHERE conversacion_id=:id AND clave_evento=:key'), {'id':thread['id'],'key':key}).scalar_one_or_none():
                _append(session,thread,origin='agente',name='Agente AARI',body=body,event=key)

    def _notice(self, session, row, source, user_id, event, message):
        if session.execute(text('SELECT notificacion_id FROM aari_visita_avisos WHERE coordinacion_id=:id AND usuario_id=:user AND evento=:event'), {'id':row['id'],'user':user_id,'event':event}).scalar_one_or_none(): return
        account = session.execute(text('SELECT email,rol::text AS rol FROM usuarios WHERE id=:id AND activo AND NOT primer_ingreso'), {'id':user_id}).mappings().one_or_none()
        if not account: return
        notification = uuid4()
        session.execute(text('''INSERT INTO notificaciones(id,reclamo_id,destinatario_tipo,destinatario_contacto,canal,
            asunto,mensaje,estado_reclamo,tipo_evento,clave_idempotencia,estado_envio,proximo_intento_en)
            VALUES (:id,:claim,:role,:email,'email',:subject,:message,
                (SELECT estado FROM reclamos WHERE id=:claim),'estado_reclamo',:key,'pendiente',clock_timestamp())'''),
            {'id':notification,'claim':row['reclamo_id'],'role':account['rol'],'email':account['email'],
             'subject':f"AARI - Coordinación de visita #{source['numero']:06d}",
             'message':message+'\nIngresá a AARI: '+visit_link(row['reclamo_id']),
             'key':f"visita:{row['id']}:{user_id}:{event}"})
        session.execute(text('INSERT INTO aari_visita_avisos(notificacion_id,coordinacion_id,usuario_id,evento) VALUES (:n,:id,:user,:event)'),
                        {'n':notification,'id':row['id'],'user':user_id,'event':event})

    def start(self, claim):
        """Puerto interno para HU20/worker; no es una acción pública de selección."""
        from app.services.visits import visits_enabled
        if not visits_enabled(): return None
        with self.transaction() as session:
            if not available(session): return None
            session.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id':claim})
            source = self._source(session, claim)
            if not _eligible(source) or source['estado'] != 'Proveedor seleccionado': return None
            old = self._row(session, claim)
            if old and self._current(old, source): return old['id']
            if old and old['etapa'] in {'esperando_disponibilidad','esperando_confirmacion','negociando','confirmada'}:
                session.execute(text("UPDATE aari_visita_coordinaciones SET etapa='invalidada',version=version+1 WHERE id=:id"), {'id':old['id']})
                self._event(session,old,'La selección o sus participantes cambiaron. Este intento queda sólo para consulta.','invalidada')
            existing=session.execute(text('SELECT id FROM aari_visita_coordinaciones WHERE reclamo_id=:id AND seleccion_id=:selection AND seleccion_version=:version'),
                                     {'id':claim,'selection':source['seleccion_id'],'version':source['updated_at']}).scalar_one_or_none()
            if existing: return existing
            row=session.execute(text('''INSERT INTO aari_visita_coordinaciones(reclamo_id,presupuesto_id,proveedor_id,
                solicitud_id,inquilino_id,inquilino_usuario_id,proveedor_usuario_id,responsable_usuario_id,contexto,seleccion_version,seleccion_id)
                VALUES (:claim,:budget,:provider,:request,:tenant,:tu,:pu,:actor,CAST(:context AS jsonb),:version,:selection) RETURNING *'''),
                {'claim':claim,'budget':source['budget'],'provider':source['proveedor_id'],'request':source['solicitud_id'],
                 'tenant':source['inquilino_id'],'tu':source['tenant_user'],'pu':source['provider_user'],'actor':source['actor_user'],
                 'context':json.dumps(_context(source)),'version':source['updated_at'],'selection':source['seleccion_id']}).mappings().one()
            for audience, participant in [('inquilino',source['tenant_user'])]+([('responsable',source['actor_user'])] if source['actor_user']!=source['tenant_user'] else []):
                session.execute(text('''INSERT INTO aari_conversaciones(finalidad,audiencia,participante_usuario_id,responsable_usuario_id,coordinacion_visita_id)
                    VALUES ('coordinacion',:audience,:user,:actor,:id)'''), {'audience':audience,'user':participant,'actor':source['actor_user'],'id':row['id']})
            self._event(session,row,'El presupuesto fue seleccionado. El inquilino debe proponer al menos tres fechas con horarios. Todavía no hay visita confirmada.','inicio')
            self._notice(session,row,source,source['tenant_user'],'inicio','El proveedor fue seleccionado. Proponé al menos tres fechas con horarios para recibirlo.')
            return row['id']

    def act(self, claim, user, action, payload):
        with self.transaction() as session:
            row, source, _, roles = self._scope(session,claim,user)
            if payload.coordinacion_id != row['id']: raise VisitError('La respuesta pertenece a otra coordinación.')
            fingerprint=hashlib.sha256(json.dumps({'accion':action,'usuario':str(user.id),'datos':payload.model_dump(mode='json')},sort_keys=True).encode()).hexdigest()
            prior=session.execute(text('SELECT huella FROM aari_visita_acciones WHERE coordinacion_id=:id AND request_id=:key'), {'id':row['id'],'key':payload.request_id}).scalar_one_or_none()
            if prior:
                if prior!=fingerprint: raise VisitError('El identificador ya se usó con otros datos.')
                return self._info(session,row,source,user,roles)|{'repetida':True}
            if row['version']!=payload.version_esperada: raise VisitError('La coordinación cambió. Actualizá antes de continuar.')
            info=self._info(session,row,source,user,roles)
            if action not in info['acciones']: raise VisitError('Esta acción no está habilitada para tu cuenta o etapa.')
            if action in FOLLOWUP_ACTIONS:
                body = apply_followup(self, session, row, source, user, action, payload, info['seguimiento'])
                updated = session.execute(text('''UPDATE aari_visita_coordinaciones SET version=version+1
                    WHERE id=:id RETURNING *'''), {'id':row['id']}).mappings().one()
                return self._record_action(session, updated, user, roles, action, payload, fingerprint, body,
                    participants_only=True)
            now=self._now(session)
            values={'id':row['id'],'next':visit_graph.invoke({'etapa':row['etapa'],'accion':action})['etapa']}
            if action=='disponibilidad':
                validate_options(payload.opciones,now)
                for option in payload.opciones:
                    session.execute(text('INSERT INTO aari_visita_opciones(coordinacion_id,desde,hasta) VALUES (:id,:start,:end)'), {'id':row['id'],'start':option.desde,'end':option.hasta})
                session.execute(text('UPDATE aari_visita_coordinaciones SET vence_en=:due WHERE id=:id'), {'id':row['id'],'due':now+timedelta(hours=24)})
                self._notice(session,row,source,row['proveedor_usuario_id'],'opciones','El inquilino propuso horarios. Confirmá uno o indicá que ninguno te sirve. Tenés 24 horas desde su publicación en AARI.')
                body='El inquilino publicó sus opciones. El proveedor tiene 24 horas para confirmar; todavía no hay visita programada.'
            elif action=='sin-coincidencia':
                body='Ningún horario le sirve al proveedor. Se habilitó la conversación con el inquilino: acuerden otro horario y confirmen la propuesta. El plazo original no se amplía.'
                self._notice(session,row,source,row['inquilino_usuario_id'],'negociando','El proveedor no puede en los horarios ofrecidos. Entrá a Mensajes para acordar otra opción y confirmarla.')
            elif action=='proponer':
                valid_time(payload.fecha,now)
                session.execute(text('''UPDATE aari_visita_coordinaciones SET propuesta_fecha=:date,propuesta_autor_id=:user,
                    propuesta_version=version+1 WHERE id=:id'''), {'id':row['id'],'date':payload.fecha,'user':user.id})
                body='Nueva propuesta: '+payload.fecha.astimezone(ARGENTINA).strftime('%d/%m/%Y a las %H:%M')+' (Argentina). La otra persona debe confirmarla mediante el botón; el mensaje no confirma la visita.'
            else:
                if row['etapa']=='negociando':
                    if payload.propuesta_version != row['propuesta_version'] or row['propuesta_autor_id']==user.id:
                        raise VisitError('Debe confirmar la otra persona y sobre la propuesta vigente.')
                    date=row['propuesta_fecha']
                else:
                    date=payload.fecha
                    if date is None or not any(o['desde']<=date<o['hasta'] for o in info['opciones']):
                        raise VisitError('Elegí una hora dentro de las opciones del inquilino.',status=422)
                valid_time(date,now)
                days=[o['desde'].astimezone(ARGENTINA).date() for o in info['opciones']]
                visit=session.execute(text('''INSERT INTO visitas(reclamo_id,proveedor_id,opciones_dias,franja_horaria_preferida,
                    fecha_confirmada,horario_confirmado,estado) VALUES (:claim,:provider,:days,'indistinto',:day,:time,'confirmada') RETURNING id'''),
                    {'claim':claim,'provider':row['proveedor_id'],'days':days,'day':date.astimezone(ARGENTINA).date(),'time':date.astimezone(ARGENTINA).strftime('%H:%M')}).scalar_one()
                session.execute(text("SELECT set_config('app.origen_reclamo',:role,true)"), {'role':user.rol})
                session.execute(text("SELECT set_config('app.usuario_reclamo',:id,true)"), {'id':str(user.id)})
                session.execute(text("UPDATE reclamos SET estado='Visita programada',fecha_visita=:date WHERE id=:id"), {'id':claim,'date':date})
                session.execute(text('''UPDATE aari_visita_coordinaciones SET etapa='confirmada',visita_id=:visit,propuesta_fecha=:date,
                    propuesta_autor_id=:user,propuesta_version=version+1 WHERE id=:id'''), {'id':row['id'],'visit':visit,'date':date,'user':user.id})
                body='Visita confirmada para '+date.astimezone(ARGENTINA).strftime('%d/%m/%Y a las %H:%M')+' (Argentina). La reparación aún no está marcada como resuelta.'
                for uid in {row['inquilino_usuario_id'],row['proveedor_usuario_id'],row['responsable_usuario_id']}:
                    self._notice(session,row,source,uid,'confirmada',body+' Dirección: '+source['direccion']+'.')
            if row['vence_en'] is not None and self._now(session)>=row['vence_en']:
                raise VisitError('Finalizó el plazo para confirmar la visita.')
            updated=session.execute(text('''UPDATE aari_visita_coordinaciones SET etapa=:next,version=version+1,
                actualizada_en=clock_timestamp() WHERE id=:id RETURNING *'''),values).mappings().one()
            return self._record_action(session, updated, user, roles, action, payload, fingerprint, body)

    def _record_action(self, session, row, user, roles, action, payload, fingerprint, body, *, participants_only=False):
        self._event(session, row, body, f"accion:{payload.request_id}", participants_only=participants_only)
        session.execute(text('''INSERT INTO aari_visita_acciones(coordinacion_id,request_id,usuario_id,accion,datos,huella,version)
            VALUES (:id,:key,:user,:action,CAST(:data AS jsonb),:fp,:version)'''),
            {'id':row['id'],'key':payload.request_id,'user':user.id,'action':action,
             'data':payload.model_dump_json(),'fp':fingerprint,'version':row['version']})
        return self._info(session,row,self._source(session,row['reclamo_id']),user,roles)|{'repetida':False}

    def tick(self, *, limit=20):
        from app.services.visits import visits_enabled
        if not visits_enabled(): return 0
        # Lectura de candidatos sin reservas por lote: cada start/action vuelve a
        # bloquear y revalidar el reclamo, sin efectos externos bajo la reserva.
        with self.transaction() as session:
            if not available(session): return 0
            ids=session.execute(text("""SELECT r.id FROM reclamos r
                JOIN reclamo_selecciones_presupuesto sp ON sp.reclamo_id=r.id
                    AND sp.presupuesto_id=r.presupuesto_seleccionado_id AND sp.proveedor_id=r.proveedor_seleccionado_id
                WHERE r.estado='Proveedor seleccionado'
                AND r.id>CAST(:cursor AS uuid)
                AND NOT EXISTS(SELECT 1 FROM aari_visita_coordinaciones c WHERE c.reclamo_id=r.id
                    AND c.seleccion_id=sp.id AND c.seleccion_version=r.updated_at)
                ORDER BY r.id LIMIT :limit"""), {'limit':max(1,min(limit,100)),
                    'cursor':str(getattr(self,'_discovery_cursor','00000000-0000-0000-0000-000000000000'))}).scalars().all()
        for claim in ids: self.start(claim)
        self._discovery_cursor=ids[-1] if ids else '00000000-0000-0000-0000-000000000000'
        with self.transaction() as session:
            ids=session.execute(text('''SELECT reclamo_id FROM aari_visita_coordinaciones
                WHERE etapa IN ('esperando_disponibilidad','esperando_confirmacion','negociando','confirmada')
                ORDER BY revisada_en,id LIMIT :limit'''), {'limit':max(1,min(limit,100))}).scalars().all()
        for claim in ids: self.follow_up(claim)
        return len(ids)

    def follow_up(self, claim):
        with self.transaction() as session:
            session.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id':claim})
            row,source=self._row(session,claim),self._source(session,claim)
            if not row: return
            session.execute(text('UPDATE aari_visita_coordinaciones SET revisada_en=clock_timestamp() WHERE id=:id'), {'id':row['id']})
            now=self._now(session)
            if 'version_horario' in row and row['etapa']=='confirmada':
                expire_proposal(session, row, now)
            if not self._current(row,source):
                if row['etapa'] not in {'invalidada','sin_acuerdo'}:
                    session.execute(text("UPDATE aari_visita_coordinaciones SET etapa='invalidada',version=version+1,actualizada_en=clock_timestamp() WHERE id=:id"), {'id':row['id']})
                    self._event(session,row,'La coordinación dejó de estar vigente. El historial se conserva y no admite nuevas acciones.','invalidada')
                return
            if row['etapa'] in WAITING and now>=row['vence_en']:
                target=visit_graph.invoke({'etapa':row['etapa'],'accion':'vencer'})['etapa']
                session.execute(text('UPDATE aari_visita_coordinaciones SET etapa=:stage,version=version+1,actualizada_en=clock_timestamp() WHERE id=:id'), {'id':row['id'],'stage':target})
                self._event(session,row,'Finalizó el plazo de 24 horas sin acuerdo. Se avisó al responsable en AARI para revisar la continuidad. No hay visita confirmada.','sin_acuerdo')
                self._notice(session,row,source,row['responsable_usuario_id'],'sin_acuerdo','No se confirmó una visita dentro de las 24 horas. Revisá cómo continuar con la selección o la coordinación.')
            elif row['etapa']=='confirmada':
                for hours in (24,2):
                    if reminder_due(row['actualizada_en'],row['propuesta_fecha'],now,hours):
                        body='Recordatorio de visita: '+row['propuesta_fecha'].astimezone(ARGENTINA).strftime('%d/%m/%Y %H:%M')+' (Argentina). Dirección: '+source['direccion']+'.'
                        event = schedule_event(f'recordatorio_{hours}', row.get('version_horario', 0))
                        for uid in (row['inquilino_usuario_id'],row['proveedor_usuario_id']): self._notice(session,row,source,uid,event,body)
                        self._event(session,row,body,event)

    def _thread_scope(self, session, thread_id, user):
        thread=session.execute(text('SELECT * FROM aari_conversaciones WHERE id=:id AND coordinacion_visita_id IS NOT NULL'), {'id':thread_id}).mappings().one_or_none()
        if not thread: raise VisitError('No encontramos esta conversación.',status=404)
        claim=session.execute(text('SELECT reclamo_id FROM aari_visita_coordinaciones WHERE id=:id'), {'id':thread['coordinacion_visita_id']}).scalar_one()
        row,source,account,roles=self._scope(session,claim,user)
        allowed=(roles['agency'] or (thread['audiencia']=='inquilino' and (roles['tenant'] or roles['provider']))
                 or (thread['audiencia']=='responsable' and roles['responsible']))
        if row['id']!=thread['coordinacion_visita_id'] or not allowed:
            raise VisitError('No encontramos esta conversación.',status=404)
        thread=session.execute(text('SELECT * FROM aari_conversaciones WHERE id=:id FOR UPDATE'), {'id':thread_id}).mappings().one()
        return thread,row,source,account,roles

    def thread_messages(self, thread_id, user, *, before=None, after=None, limit=30):
        from app.db.conversations import SqlAlchemyConversations
        if before is not None and after is not None: raise VisitError('Usá un solo sentido de paginación.',status=422)
        with self.transaction() as session:
            thread,row,source,_,roles=self._thread_scope(session,thread_id,user)
            direction='ASC' if after is not None else 'DESC'
            bound=' AND numero>:cursor' if after is not None else ' AND numero<:cursor' if before is not None else ''
            rows=session.execute(text('''SELECT id,numero,origen,autor_id,autor_nombre,texto,creado_en FROM aari_conversacion_mensajes
                WHERE conversacion_id=:id'''+bound+' ORDER BY numero '+direction+' LIMIT :limit'),
                {'id':thread_id,'cursor':after if after is not None else before,'limit':limit+1}).mappings().all()
            more,rows=len(rows)>limit,rows[:limit]
            if after is None: rows=rows[::-1]
            read,unread=SqlAlchemyConversations._reader(session,thread,user.id,audit=roles['agency'])
            info=self._info(session,row,source,user,roles)
            return {'id':thread_id,'solicitud_id':None,'reclamo_id':row['reclamo_id'],'finalidad':'coordinacion',
                'numero_reclamo':source['numero'],'puede_enviar':info['puede_conversar'] and thread['audiencia']=='inquilino',
                'motivo_solo_lectura':info['motivo_solo_lectura'] or 'Las fechas se proponen y confirman con las acciones de coordinación.',
                'puede_finalizar':False,'coordinacion_url':f"/visitas/{row['reclamo_id']}",
                'ultimo_numero':thread['ultimo_numero'],'leido_hasta':read,'no_leidos':unread,
                'hay_anteriores':more if after is None else False,'hay_nuevos':more if after is not None else False,
                'items':[SqlAlchemyConversations._message(item,user.id) for item in rows]}

    def thread_send(self, thread_id, user, payload):
        from app.db.conversations import _append, SqlAlchemyConversations
        with self.transaction() as session:
            thread,row,source,account,roles=self._thread_scope(session,thread_id,user)
            previous=session.execute(text('SELECT * FROM aari_conversacion_mensajes WHERE conversacion_id=:id AND autor_id=:user AND request_id=:key'),
                {'id':thread_id,'user':user.id,'key':payload.request_id}).mappings().one_or_none()
            if previous:
                if previous['texto']!=payload.texto: raise VisitError('Ese envío ya se usó con otro texto.')
                return {'mensaje':SqlAlchemyConversations._message(previous,user.id),'repetido':True}
            info=self._info(session,row,source,user,roles)
            if not info['puede_conversar'] or thread['audiencia']!='inquilino': raise VisitError('Esta conversación está en sólo lectura.',status=403)
            message=_append(session,thread,origin='humano',name=account['nombre_completo'] or ('Proveedor' if roles['provider'] else 'Inquilino'),
                            body=payload.texto,actor=user.id,request=payload.request_id)
            return {'mensaje':SqlAlchemyConversations._message(message,user.id),'repetido':False}

    def thread_read(self, thread_id, user, through):
        from app.db.conversations import SqlAlchemyConversations
        with self.transaction() as session:
            thread,_,_,_,roles=self._thread_scope(session,thread_id,user)
            if through>thread['ultimo_numero']: raise VisitError('No se pueden marcar mensajes futuros como leídos.',status=422)
            value=session.execute(text('''INSERT INTO aari_conversacion_lecturas(conversacion_id,usuario_id,ultimo_numero)
                VALUES (:id,:user,:number) ON CONFLICT(conversacion_id,usuario_id) DO UPDATE
                SET ultimo_numero=greatest(aari_conversacion_lecturas.ultimo_numero,excluded.ultimo_numero) RETURNING ultimo_numero'''),
                {'id':thread_id,'user':user.id,'number':through}).scalar_one()
            return {'leido_hasta':value,'no_leidos':SqlAlchemyConversations._reader(session,thread,user.id,audit=roles['agency'])[1]}


def coordination_thread(session, thread_id):
    from app.services.visits import visits_enabled
    return (visits_enabled() and available(session) and session.execute(text(
        'SELECT id FROM aari_conversaciones WHERE id=:id AND coordinacion_visita_id IS NOT NULL'), {'id':thread_id}).scalar_one_or_none() is not None)


def inbox_select(user):
    """Rama SQL del UNION: misma paginación global y sin N+1 por tarjeta."""
    scopes={
        'inquilino':"c.audiencia='inquilino' AND v.inquilino_usuario_id=:user AND i.usuario_id=:user AND i.id=:profile AND i.estado='activo' AND i.propiedad_id=r.propiedad_id",
        'proveedor':"c.audiencia='inquilino' AND v.proveedor_usuario_id=:user AND pr.usuario_id=:user AND pr.id=:profile AND pr.activo",
        'propietario':"c.audiencia='responsable' AND v.responsable_usuario_id=:user AND owner.usuario_id=:user",
        'administrador':'true','operador':'r.operador_asignado_id=:user',
    }
    return '''SELECT c.id,c.solicitud_id,c.finalidad,c.audiencia,r.numero,pr.nombre_razon_social AS proveedor,
        c.actualizada_en,c.consultas_cerradas_en,
        CASE WHEN :audit THEN 0 ELSE (SELECT count(*) FROM aari_conversacion_mensajes m
            WHERE m.conversacion_id=c.id AND m.numero>coalesce(l.ultimo_numero,0)
            AND m.autor_id IS DISTINCT FROM :user) END AS no_leidos
        FROM aari_conversaciones c JOIN aari_visita_coordinaciones v ON v.id=c.coordinacion_visita_id
        JOIN reclamos r ON r.id=v.reclamo_id JOIN inquilinos i ON i.id=v.inquilino_id
        JOIN propiedades p ON p.id=r.propiedad_id JOIN propietarios owner ON owner.id=p.propietario_id
        JOIN proveedores pr ON pr.id=v.proveedor_id
        LEFT JOIN aari_conversacion_lecturas l ON l.conversacion_id=c.id AND l.usuario_id=:user
        WHERE v.seleccion_id IS NOT NULL
        AND v.id=(SELECT x.id FROM aari_visita_coordinaciones x WHERE x.reclamo_id=r.id ORDER BY x.creada_en DESC,x.id DESC LIMIT 1)
        AND ('''+scopes.get(user.rol,'false')+')'


def validate_visit_notice(session, notification_id):
    """Revalidar vínculo, etapa, reloj y destinatario antes de SMTP."""
    if not available(session): return True
    notice=session.execute(text('''SELECT a.*,n.destinatario_contacto,n.destinatario_tipo,u.email,u.rol::text AS rol,
        u.activo AND NOT u.primer_ingreso AS active FROM aari_visita_avisos a
        JOIN notificaciones n ON n.id=a.notificacion_id JOIN usuarios u ON u.id=a.usuario_id WHERE n.id=:id'''), {'id':notification_id}).mappings().one_or_none()
    if not notice: return True
    row=session.execute(text('SELECT * FROM aari_visita_coordinaciones WHERE id=:id'), {'id':notice['coordinacion_id']}).mappings().one()
    repo=SqlAlchemyVisits()
    source=repo._source(session,row['reclamo_id'])
    now=repo._now(session)
    from app.services.visits import visits_enabled
    valid=(visits_enabled() and notice['active'] and notice['email']==notice['destinatario_contacto']
           and notice['rol']==notice['destinatario_tipo'] and repo._current(row,source))
    event=notice['evento']
    if event=='inicio': valid=valid and row['etapa']=='esperando_disponibilidad'
    elif event in {'opciones','negociando'}: valid=valid and row['etapa'] in WAITING and now<row['vence_en']
    elif event=='sin_acuerdo': valid=valid and row['etapa']=='sin_acuerdo'
    else: valid=valid and notice_matches_schedule(session, row, event, now)
    if not valid:
        session.execute(text('''UPDATE notificaciones SET estado_envio='fallido',ultimo_error='Coordinación de visita no vigente; aviso obsoleto.',
            proximo_intento_en=NULL,bloqueado_hasta=NULL,updated_at=clock_timestamp()
            WHERE id=:id AND estado_envio IN ('pendiente','procesando')'''), {'id':notification_id})
    return bool(valid)


def visit_link(claim):
    import os
    from urllib.parse import urlsplit
    base=os.getenv('APP_LOGIN_URL','http://localhost:5173/login')
    parsed=urlsplit(base)
    if parsed.scheme not in {'http','https'} or not parsed.netloc or parsed.username or parsed.password:
        raise VisitError('Falta configurar la dirección pública de AARI.',status=503)
    return f'{parsed.scheme}://{parsed.netloc}/visitas/{claim}'
