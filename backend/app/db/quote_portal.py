"""Canal AARI privado. No usa teléfono, mensajes de Meta ni llamadas de red."""

import json
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app.db.quote_requests import COLUMNS, SOURCE, ELIGIBLE, SqlAlchemyQuoteRequests
from app.db.reclamos import SqlAlchemyClaimsRepository
from app.services.quote_requests import request_content
from app.services.quote_portal import QuotePortalError, portal_link


REQUEST_FROM = """ FROM public.aari_solicitudes_presupuesto s
    JOIN public.aari_rondas_presupuesto rp ON rp.id=s.ronda_id
    JOIN public.reclamos r ON r.id=s.reclamo_id
    JOIN public.proveedores p ON p.id=s.proveedor_id
    LEFT JOIN public.notificaciones n ON n.id=s.aviso_id
    LEFT JOIN public.presupuestos b ON b.solicitud_aari_id=s.id """

REQUEST_SELECT = """SELECT s.*, rp.contexto, rp.huella, rp.eleccion_id, rp.estado AS ronda_estado,
    rp.cerrada_en, r.numero, p.nombre_razon_social AS proveedor_nombre,
    n.estado_envio AS aviso_estado, b.id AS presupuesto_id, b.monto, b.moneda,
    b.tipo_importe, b.descripcion AS trabajo, b.recibido_en""" + REQUEST_FROM


class SqlAlchemyQuotePortal(SqlAlchemyQuoteRequests):
    @staticmethod
    def _event(s, round_id, kind, *, request_id=None, actor=None):
        s.execute(text('''INSERT INTO aari_presupuesto_eventos(ronda_id,solicitud_id,actor_id,tipo)
            VALUES (:round,:request,:actor,:kind)'''),
            {'round':round_id,'request':request_id,'actor':actor,'kind':kind})

    @staticmethod
    def _mail(s, claim_id, role, email, key, message):
        return s.execute(text('''INSERT INTO notificaciones
            (reclamo_id,destinatario_tipo,destinatario_contacto,canal,asunto,mensaje,
             estado_reclamo,tipo_evento,clave_idempotencia,estado_envio,proximo_intento_en)
            VALUES (:claim,:role,:email,'email','AARI - Presupuestos',:message,
             (SELECT estado FROM reclamos WHERE id=:claim),'estado_reclamo',:key,'pendiente',clock_timestamp())
            ON CONFLICT (clave_idempotencia) WHERE clave_idempotencia IS NOT NULL
            DO UPDATE SET clave_idempotencia=excluded.clave_idempotencia RETURNING id'''),
            {'claim':claim_id,'role':role,'email':email,'key':key,'message':message}).scalar_one()

    @classmethod
    def _operator_notice(cls, s, claim_id, round_id, reason):
        operator_id = s.execute(text('SELECT operador_asignado_id FROM reclamos WHERE id=:id'), {'id':claim_id}).scalar_one()
        recipient = SqlAlchemyClaimsRepository._operator_recipient(s, assigned_operator_id=operator_id)
        if recipient:
            cls._mail(s, claim_id, recipient['rol'], recipient['email'], f'aari-quote:{round_id}:{reason}',
                      'La ronda de presupuestos requiere revisión de la inmobiliaria: '+reason+'. Ingresá a AARI.')

    def publish(self, claim_id):
        with self.transaction() as s:
            s.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id':str(claim_id)})
            row = self._eligible(s, claim_id)
            if row is None: return {'publicadas':0, 'motivo':'reclamo_no_habilitado'}
            content, digest = request_content(row)
            previous = s.execute(text('''SELECT rp.*, EXISTS (
                SELECT 1 FROM aari_solicitudes_presupuesto q WHERE q.ronda_id=rp.id
                ) AS tiene_solicitudes FROM aari_rondas_presupuesto rp
                WHERE rp.eleccion_id=:id FOR UPDATE OF rp'''),
                {'id':row['eleccion_id']}).mappings().one_or_none()
            if previous and not (previous['estado']=='revision' and previous['vence_en'] is None
                    and previous['cerrada_en'] is not None and not previous['tiene_solicitudes']
                    and previous['huella']==digest):
                return {'publicadas':0, 'repetida':True}
            candidates = self._candidates(s, row)
            providers = []
            if candidates:
                providers = s.execute(text('''SELECT p.id,p.usuario_id,p.email,
                    (u.id IS NOT NULL AND u.rol::text='proveedor' AND u.activo AND NOT u.primer_ingreso
                     AND u.email=p.email) AS habilitado FROM proveedores p
                    LEFT JOIN usuarios u ON u.id=p.usuario_id WHERE p.id IN :ids ORDER BY p.id''')
                    .bindparams(bindparam('ids', expanding=True)), {'ids':candidates}).mappings().all()
            enabled = [p for p in providers if p['habilitado']]
            exclusions = [{'proveedor_id':str(p['id']),'motivo':'sin_acceso_activado'} for p in providers if not p['habilitado']]
            if previous and not enabled:
                # No escribir eventos ni avisos en cada sondeo sin novedades.
                return {'publicadas':0, 'repetida':True}
            now = s.execute(text('SELECT clock_timestamp()')).scalar_one()
            round_id = previous['id'] if previous else uuid4()
            if previous:
                # Primera publicación real: las exclusiones/contexto originales y
                # el evento de revisión quedan intactos. Nunca rejuvenecer una
                # ronda que haya tenido solicitudes, respuestas o vencimiento.
                s.execute(text('''UPDATE aari_rondas_presupuesto SET estado='esperando',
                    publicada_en=:now,vence_en=:now+interval '24 hours',cerrada_en=NULL
                    WHERE id=:id'''), {'id':round_id,'now':now})
            else:
                s.execute(text('''INSERT INTO aari_rondas_presupuesto
                (id,reclamo_id,eleccion_id,huella,contexto,exclusiones,estado,publicada_en,vence_en,cerrada_en)
                VALUES (:id,:claim,:choice,:digest,CAST(:context AS jsonb),CAST(:excluded AS jsonb),
                    :state,:now,CASE WHEN :count>0 THEN :now+interval '24 hours' ELSE NULL END,
                    CASE WHEN :count=0 THEN :now ELSE NULL END)'''),
                    {'id':round_id,'claim':claim_id,'choice':row['eleccion_id'],'digest':digest,
                     'context':json.dumps(content),'excluded':json.dumps(exclusions),'state':'esperando' if enabled else 'revision',
                     'now':now,'count':len(enabled)})
            for p in enabled:
                request_id = uuid4()
                s.execute(text('''INSERT INTO aari_solicitudes_presupuesto
                    (id,ronda_id,reclamo_id,proveedor_id,usuario_id,publicada_en,vence_en)
                    VALUES (:id,:round,:claim,:provider,:user,:now,:now+interval '24 hours')'''),
                    {'id':request_id,'round':round_id,'claim':claim_id,'provider':p['id'],'user':p['usuario_id'],'now':now})
                notice = self._mail(s,claim_id,'proveedor',p['email'],f'aari-quote:{request_id}:publicada',
                    'Tenés una solicitud de presupuesto en AARI. Ingresá para consultar el detalle y el plazo: '+
                    portal_link('/proveedor/solicitudes/'+str(request_id)))
                s.execute(text('UPDATE aari_solicitudes_presupuesto SET aviso_id=:notice WHERE id=:id'),
                          {'notice':notice,'id':request_id})
                self._event(s,round_id,'publicada',request_id=request_id)
            if not previous and (exclusions or not enabled):
                self._operator_notice(s,claim_id,round_id,'candidatos_sin_acceso' if exclusions else 'sin_candidatos')
                self._event(s,round_id,'revision')
            return {'ronda_id':round_id,'publicadas':len(enabled),'excluidas':len(exclusions),
                    'recuperada':previous is not None}

    def discover_portal(self, limit=20):
        limit=max(1,min(100,int(limit)))
        cursor=None
        publications=processed=0
        while processed<limit:
            with self.transaction() as s:
                scope = ' AND r.id=:scope' if self.scope_claim_id else ''
                after = ' AND (ep.decidido_en,r.id)>(:decided,CAST(:last AS uuid))' if cursor else ''
                rows = s.execute(text('SELECT r.id,ep.decidido_en '+SOURCE+' WHERE '+ELIGIBLE+''' AND (
                    NOT EXISTS (SELECT 1 FROM aari_rondas_presupuesto rp WHERE rp.eleccion_id=ep.id)
                    OR EXISTS (SELECT 1 FROM aari_rondas_presupuesto rp
                        WHERE rp.eleccion_id=ep.id AND rp.estado='revision' AND rp.vence_en IS NULL
                        AND rp.cerrada_en IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM aari_solicitudes_presupuesto q WHERE q.ronda_id=rp.id))) '''+scope+after+
                    ' ORDER BY ep.decidido_en,r.id LIMIT :limit'),
                    {'scope':self.scope_claim_id,'limit':limit,
                     'decided':cursor[0] if cursor else None,'last':str(cursor[1]) if cursor else None}).mappings().all()
            if not rows:
                break
            for row in rows:
                result=self.publish(row['id'])
                publications+=result.get('publicadas',0)
                processed+=not result.get('repetida',False)
                cursor=(row['decidido_en'],row['id'])
                if processed>=limit:
                    break
            # Paginación por clave: las rondas aún sin acceso no bloquean las
            # que sí pueden recuperarse después, ni se generan avisos repetidos.
        return publications

    def _current(self, s, request):
        row = self._eligible(s, request['reclamo_id'])
        return (row is not None and row['eleccion_id']==request['eleccion_id']
                and request_content(row)[1]==request['huella']
                and request['proveedor_id'] in self._candidates(s,row))

    @staticmethod
    def _state(row, now):
        if row['ronda_estado']=='cancelada': return 'cancelada'
        if row['presupuesto_id']: return 'respondida'
        return 'vencida' if row['cerrada_en'] or now>=row['vence_en'] else 'pendiente'

    def _view(self, s, row, now, *, can_respond=None):
        state = self._state(row,now)
        return {'id':row['id'],'reclamo_id':row['reclamo_id'],'numero':row['numero'],
            'descripcion':row['contexto']['descripcion'],'ubicacion':row['contexto']['ubicacion'],
            'publicada_en':row['publicada_en'],'vence_en':row['vence_en'],'estado':state,
            'puede_responder':state=='pendiente' and (self._current(s,row) if can_respond is None else can_respond),
            'presupuesto':None if not row['presupuesto_id'] else {
                'id':row['presupuesto_id'],'monto':str(row['monto']),'moneda':row['moneda'],
                'tipo_importe':row['tipo_importe'],'descripcion':row['trabajo'],'recibido_en':row['recibido_en']}}

    def _actionable_rows(self, s, rows):
        """Revalida contexto y compatibilidad antes de contar/paginar pendientes.

        SQL ya excluyó respondidas, cerradas y vencidas. Se carga el contexto
        vigente en lote y se comparte la búsqueda por especialidad/cobertura,
        sin una consulta por cada solicitud ni una regla paralela de vigencia.
        """
        if not rows:
            return []
        ids=list({row['reclamo_id'] for row in rows})
        contexts=s.execute(text('SELECT '+COLUMNS+SOURCE+' WHERE r.id IN :ids AND '+ELIGIBLE)
            .bindparams(bindparam('ids',expanding=True)),{'ids':ids}).mappings().all()
        contexts={row['id']:row for row in contexts}
        compatible={}
        result=[]
        for row in rows:
            current=contexts.get(row['reclamo_id'])
            if current is None or current['eleccion_id']!=row['eleccion_id'] or request_content(current)[1]!=row['huella']:
                continue
            key=tuple(current[field] for field in ('tipo_id','provincia','localidad','barrio'))
            if key not in compatible:
                compatible[key]=set(self._candidates(s,current))
            if row['proveedor_id'] in compatible[key]:
                result.append(row)
        return result

    def list_own(self, user, page=1, page_size=10, *, status='pendientes'):
        if status not in {'pendientes','enviadas','todas'}:
            raise QuotePortalError('El filtro de solicitudes no es válido.',status=422,code='invalid_filter')
        with self.transaction() as s:
            where = ' WHERE s.usuario_id=:user AND s.proveedor_id=:provider AND p.usuario_id=:user AND p.activo'
            params={'user':user.id,'provider':user.perfil_id,'limit':page_size,'offset':(page-1)*page_size}
            now=s.execute(text('SELECT clock_timestamp()')).scalar_one()
            if status=='pendientes':
                where+=' AND b.id IS NULL AND rp.estado<>\'cancelada\' AND rp.cerrada_en IS NULL AND s.vence_en>:now'
                rows=s.execute(text(REQUEST_SELECT+where+' ORDER BY s.publicada_en DESC,s.id DESC'),
                    {**params,'now':now}).mappings().all()
                rows=self._actionable_rows(s,rows)
                total=len(rows)
                rows=rows[params['offset']:params['offset']+page_size]
            else:
                if status=='enviadas':
                    where+=' AND b.id IS NOT NULL'
                total=s.execute(text('SELECT count(*)'+REQUEST_FROM+where),params).scalar_one()
                rows=s.execute(text(REQUEST_SELECT+where+' ORDER BY s.publicada_en DESC,s.id DESC LIMIT :limit OFFSET :offset'),params).mappings().all()
            return {'items':[self._view(s,r,now,can_respond=True if status=='pendientes' else None) for r in rows],
                'total':total,'page':page,'page_size':page_size,'estado':status}

    @staticmethod
    def _own(s, request_id, user):
        row=s.execute(text(REQUEST_SELECT+''' WHERE s.id=:id AND s.usuario_id=:user
            AND s.proveedor_id=:provider AND p.usuario_id=:user AND p.activo'''),
            {'id':request_id,'user':user.id,'provider':user.perfil_id}).mappings().one_or_none()
        if row is None: raise QuotePortalError('No encontramos esa solicitud.',status=404,code='request_not_found')
        return row

    def get_own(self, request_id, user):
        with self.transaction() as s:
            row=self._own(s,request_id,user)
            return self._view(s,row,s.execute(text('SELECT clock_timestamp()')).scalar_one())

    def submit(self, request_id, user, payload):
        try:
            with self.transaction() as s:
                first=self._own(s,request_id,user)
                s.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'),{'id':first['reclamo_id']})
                s.execute(text('SELECT id FROM aari_solicitudes_presupuesto WHERE id=:id FOR UPDATE'),{'id':request_id})
                row=self._own(s,request_id,user)
                now=s.execute(text('SELECT clock_timestamp()')).scalar_one()
                if row['presupuesto_id']:
                    if (row['respuesta_request_id']==payload.request_id and row['monto']==payload.monto
                        and row['moneda']==payload.moneda and row['tipo_importe']==payload.tipo_importe
                        and row['trabajo']==payload.descripcion): return self._view(s,row,now)
                    raise QuotePortalError('Esta solicitud ya tiene un presupuesto confirmado.',code='already_quoted')
                if self._state(row,now)!='pendiente' or not self._current(s,row):
                    raise QuotePortalError('La solicitud venció o ya no está habilitada para responder.',code='request_unavailable')
                s.execute(text('''INSERT INTO presupuestos(reclamo_id,proveedor_id,monto,moneda,tipo_importe,
                    descripcion,recibido_en,solicitud_aari_id,presentado_por)
                    VALUES (:claim,:provider,:amount,:currency,:kind,:description,:now,:request,:user)'''),
                    {'claim':row['reclamo_id'],'provider':row['proveedor_id'],'amount':payload.monto,
                     'currency':payload.moneda,'kind':payload.tipo_importe,'description':payload.descripcion,
                     'now':now,'request':request_id,'user':user.id})
                s.execute(text('UPDATE aari_solicitudes_presupuesto SET respuesta_request_id=:key WHERE id=:id'),
                          {'key':payload.request_id,'id':request_id})
                self._event(s,row['ronda_id'],'presupuesto_registrado',request_id=request_id,actor=user.id)
                actor=s.execute(text('''SELECT u.email,u.rol::text AS rol FROM reclamo_elecciones_proveedor ep
                    JOIN usuarios u ON u.id=ep.usuario_id WHERE ep.id=:id AND u.activo'''),{'id':row['eleccion_id']}).mappings().one_or_none()
                if actor:
                    self._mail(s,row['reclamo_id'],actor['rol'],actor['email'],f"aari-quote:{row['ronda_id']}:disponible",
                        'Hay al menos un presupuesto disponible en AARI. Puede ser exacto o un importe mínimo; no confirma contratación. '+
                        portal_link('/'+actor['rol']+'/reclamos/'+str(row['reclamo_id'])+'/tipo-proveedor'))
                return self._view(s,self._own(s,request_id,user),now)
        except IntegrityError:
            raise QuotePortalError('La operación ya fue registrada. Actualizá la solicitud antes de reintentar.') from None

    def for_claim(self, claim_id, user):
        with self.transaction() as s:
            claim=s.execute(text('''SELECT r.operador_asignado_id,rr.actor_tipo,
                CASE WHEN rr.actor_tipo='inquilino' AND i.estado='activo' AND i.propiedad_id=r.propiedad_id
                     THEN i.usuario_id WHEN rr.actor_tipo='propietario' THEN pr.usuario_id END AS actor_id,
                rr.solicitado_en
                FROM reclamos r JOIN reclamo_responsables rr ON rr.reclamo_id=r.id
                JOIN inquilinos i ON i.id=r.inquilino_id JOIN propiedades p ON p.id=r.propiedad_id
                JOIN propietarios pr ON pr.id=p.propietario_id WHERE r.id=:id'''),{'id':claim_id}).mappings().one_or_none()
            if not claim or not (user.rol=='administrador' or
                (user.rol=='operador' and user.id==claim['operador_asignado_id']) or
                (user.rol in {'inquilino','propietario'} and user.id==claim['actor_id'] and user.rol==claim['actor_tipo'])):
                raise QuotePortalError('No encontramos ese reclamo.',status=404,code='claim_not_found')
            agency=user.rol in {'administrador','operador'}
            scope='' if agency else ''' AND EXISTS (SELECT 1 FROM reclamo_elecciones_proveedor ep
                WHERE ep.id=rp.eleccion_id AND ep.usuario_id=:actor
                AND ep.solicitud_responsable_en=:cycle)'''
            rows=s.execute(text(REQUEST_SELECT+' WHERE s.reclamo_id=:id'+scope+' ORDER BY s.publicada_en DESC,s.id'),
                {'id':claim_id,'actor':user.id,'cycle':claim['solicitado_en']}).mappings().all()
            now=s.execute(text('SELECT clock_timestamp()')).scalar_one()
            return {'items':[{**self._view(s,r,now),'puede_responder':False,'proveedor':r['proveedor_nombre'],
                **({'aviso_estado':r['aviso_estado']} if user.rol in {'administrador','operador'} else {})} for r in rows]}

    def finalize_due_portal(self, limit=20):
        with self.transaction() as s:
            ids=s.execute(text('''SELECT id,reclamo_id FROM aari_rondas_presupuesto
                WHERE cerrada_en IS NULL AND vence_en<=clock_timestamp() ORDER BY vence_en,id LIMIT :limit'''),{'limit':limit}).mappings().all()
        return sum(self.finalize_one_portal(r['id'],r['reclamo_id']) for r in ids)

    def finalize_one_portal(self, round_id, claim_id):
        with self.transaction() as s:
            s.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'),{'id':claim_id})
            row=s.execute(text('SELECT * FROM aari_rondas_presupuesto WHERE id=:id FOR UPDATE'),{'id':round_id}).mappings().one_or_none()
            now=s.execute(text('SELECT clock_timestamp()')).scalar_one()
            if not row or row['cerrada_en'] or row['vence_en'] is None or now<row['vence_en']: return False
            context=self._eligible(s,claim_id)
            valid=context is not None and context['eleccion_id']==row['eleccion_id'] and request_content(context)[1]==row['huella']
            counts=s.execute(text('''SELECT count(b.id) AS quotes,
                count(*) FILTER (WHERE n.estado_envio IS DISTINCT FROM 'enviado') AS failures
                FROM aari_solicitudes_presupuesto q LEFT JOIN presupuestos b ON b.solicitud_aari_id=q.id
                LEFT JOIN notificaciones n ON n.id=q.aviso_id WHERE q.ronda_id=:id'''),{'id':round_id}).mappings().one()
            state='cancelada' if not valid else 'disponibles' if counts['quotes'] else 'revision' if counts['failures'] else 'sin_presupuestos'
            s.execute(text('UPDATE aari_rondas_presupuesto SET estado=:state,cerrada_en=:now WHERE id=:id'),{'state':state,'now':now,'id':round_id})
            self._event(s,round_id,'cancelada' if not valid else 'vencida')
            if state=='sin_presupuestos':
                s.execute(text("SELECT set_config('app.origen_reclamo','agente',true)"))
                s.execute(text("UPDATE reclamos SET estado='Sin presupuestos recibidos' WHERE id=:id"),{'id':claim_id})
            if state in {'sin_presupuestos','revision'}: self._operator_notice(s,claim_id,round_id,state)
            return True
