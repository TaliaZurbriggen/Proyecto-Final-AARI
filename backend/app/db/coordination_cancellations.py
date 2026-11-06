"""HU24: cancelar y abrir una nueva elección en una sola transacción."""

from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.agents.coordination.cancellation import cancellation_graph
from app.db.provider_choices import SqlAlchemyProviderChoicesRepository
from app.db.quote_portal import SqlAlchemyQuotePortal
from app.services.coordination_cancellations import cancellation_reason
from app.services.provider_choices_service import ProviderChoiceForbidden, ProviderChoiceNotFound
from app.services.quote_portal import QuotePortalError, portal_link
from app.services.conversations import conversations_enabled


def _conflict(message='El reclamo cambió. Actualizá antes de cancelar.'):
    return QuotePortalError(message, code='cancellation_conflict')


def _result(row, *, repeated=False):
    return {k: row[k] for k in ('id','reclamo_id','eleccion_id','eleccion_nueva_id',
        'actor_nombre','estado_anterior','estado_resultante','creada_en')} | {'repetida': repeated}


class SqlAlchemyCoordinationCancellations(SqlAlchemyQuotePortal):
    @staticmethod
    def _available(s):
        if not s.execute(text("SELECT to_regclass('public.reclamo_cancelaciones_coordinacion') IS NOT NULL")).scalar_one():
            raise QuotePortalError('La cancelación todavía no está habilitada.',status=503,code='cancellation_unavailable')

    @staticmethod
    def _access(s, claim_id, user, *, lock=False):
        try:
            params = SqlAlchemyProviderChoicesRepository._params(claim_id, user)
            # Orden compartido con HU17/HU18/HU20: cuenta, perfil, propiedad,
            # reclamo y elección. El bloqueo de reclamo serializa HU23 también.
            account = s.execute(text('''SELECT id FROM usuarios WHERE id=:user
                AND rol::text=:role AND activo AND NOT primer_ingreso FOR SHARE'''),params).scalar_one_or_none()
            if account is None:
                raise ProviderChoiceForbidden
            table = 'inquilinos' if user.rol=='inquilino' else 'propietarios'
            s.execute(text(f'SELECT id FROM {table} WHERE id=:profile AND usuario_id=:user FOR SHARE'),params).all()
            s.execute(text('''SELECT p.id FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id
                WHERE r.id=:id FOR SHARE OF p'''),params).all()
            if lock:
                s.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'),params).all()
            row = SqlAlchemyProviderChoicesRepository._row(s,params,lock=lock)
            return dict(row)
        except ProviderChoiceForbidden:
            raise QuotePortalError('La cuenta no puede cancelar.',status=403,code='forbidden') from None
        except ProviderChoiceNotFound:
            raise QuotePortalError('No encontramos ese reclamo para tu cuenta.',status=404,code='claim_not_found') from None

    @staticmethod
    def _context(s, row, user):
        auth = row['tipo_gasto']=='ordinario' or s.execute(text('''SELECT EXISTS(
            SELECT 1 FROM reclamo_autorizaciones a JOIN reclamo_responsables rr ON rr.reclamo_id=a.reclamo_id
            WHERE a.reclamo_id=:claim AND a.solicitado_en=rr.solicitado_en
              AND a.usuario_id=:user AND a.decision='autorizar' AND a.estado='Autorizado')'''),
            {'claim':row['reclamo_id'],'user':user.id}).scalar_one()
        scheduled = s.execute(text('''SELECT fecha_visita IS NOT NULL OR EXISTS(
            SELECT 1 FROM visitas v WHERE v.reclamo_id=r.id AND v.estado IN ('confirmada','realizada'))
            FROM reclamos r WHERE r.id=:id'''),{'id':row['reclamo_id']}).scalar_one()
        if s.execute(text("SELECT to_regclass('public.aari_visita_coordinaciones') IS NOT NULL")).scalar_one():
            scheduled = scheduled or s.execute(text("SELECT EXISTS(SELECT 1 FROM aari_visita_coordinaciones WHERE reclamo_id=:id AND etapa='confirmada')"),
                                               {'id':row['reclamo_id']}).scalar_one()
        reason = cancellation_reason(row,authorized=bool(auth),visit_scheduled=bool(scheduled))
        if not reason and row['estado']=='Proveedor seleccionado' and not s.execute(text('''SELECT EXISTS(
            SELECT 1 FROM reclamo_selecciones_presupuesto a JOIN reclamos r ON r.id=a.reclamo_id
            WHERE a.reclamo_id=:claim AND a.eleccion_id=:choice AND a.usuario_id=:user
              AND r.proveedor_seleccionado_id=a.proveedor_id AND r.presupuesto_seleccionado_id=a.presupuesto_id
              AND r.monto_seleccionado=a.monto)'''),
            {'claim':row['reclamo_id'],'choice':row['solicitud_id'],'user':user.id}).scalar_one():
            reason='La selección no corresponde al intento vigente. Consultá a la inmobiliaria.'
        if not reason and str(row['usuario_id'])!=str(user.id):
            reason='La elección ya no corresponde a tu cuenta.'
        return reason

    def get(self, claim_id, user):
        with self.transaction() as s:
            self._available(s)
            row=self._access(s,claim_id,user)
            reason=self._context(s,row,user)
            history=s.execute(text('''SELECT c.id,c.etapa,c.timestamp,p.nombre_razon_social AS proveedor,
                a.actor_nombre FROM cancelaciones c LEFT JOIN proveedores p ON p.id=c.proveedor_id
                LEFT JOIN reclamo_cancelaciones_coordinacion a ON a.id=c.id
                WHERE c.reclamo_id=:id ORDER BY c.timestamp DESC,c.id DESC'''),{'id':claim_id}).mappings().all()
            return {'reclamo_id':claim_id,'numero':row['numero'],'descripcion':row['descripcion'],
                    'estado':row['estado'],'updated_at':row['updated_at'],'eleccion_id':row['solicitud_id'],
                    'puede_cancelar':reason is None,'motivo_bloqueo':reason,'historial':[dict(x) for x in history]}

    def cancel(self, claim_id, user, payload):
        try:
            with self.transaction() as s:
                self._available(s)
                row=self._access(s,claim_id,user,lock=True)
                old=s.execute(text('SELECT * FROM reclamo_cancelaciones_coordinacion WHERE request_id=:id'),
                              {'id':payload.request_id}).mappings().one_or_none()
                if old:
                    if (old['reclamo_id']!=claim_id or old['usuario_id']!=user.id
                            or old['eleccion_id']!=payload.eleccion_id
                            or old['expected_updated_at']!=payload.expected_updated_at or not payload.confirmar):
                        raise _conflict('El identificador ya se utilizó para otra cancelación.')
                    return _result(old,repeated=True)
                reason=self._context(s,row,user)
                if reason:
                    raise _conflict(reason)
                if (not payload.confirmar or payload.eleccion_id!=row['solicitud_id']
                        or payload.expected_updated_at!=row['updated_at']):
                    raise _conflict()
                round_row=s.execute(text('SELECT * FROM aari_rondas_presupuesto WHERE eleccion_id=:id FOR UPDATE'),
                                    {'id':row['solicitud_id']}).mappings().one_or_none()
                selected=s.execute(text('''SELECT proveedor_seleccionado_id FROM reclamos WHERE id=:id'''),
                                   {'id':claim_id}).scalar_one()
                stage=('esperando_confirmacion_disponibilidad' if row['estado']=='Proveedor seleccionado'
                    else 'revisando_presupuestos' if round_row and s.execute(text('''SELECT EXISTS(
                        SELECT 1 FROM presupuestos b JOIN aari_solicitudes_presupuesto q ON q.id=b.solicitud_aari_id
                        WHERE q.ronda_id=:id)'''),{'id':round_row['id']}).scalar_one() else 'esperando_presupuestos')
                cancellation_id,new_choice=uuid4(),uuid4()
                # Nunca reiniciar el ciclo rr ni la autorización extraordinaria.
                # La nueva elección recibe su propio plazo HU17 de 48/72 h.
                now=s.execute(text("SELECT greatest(clock_timestamp(),:previous+interval '1 microsecond')"),
                              {'previous':row['solicitado_en']}).scalar_one()
                cycle=s.execute(text('SELECT solicitud_responsable_en,intento FROM reclamo_elecciones_proveedor WHERE id=:id'),
                                {'id':row['solicitud_id']}).mappings().one()
                s.execute(text('''INSERT INTO reclamo_elecciones_proveedor(id,reclamo_id,solicitud_responsable_en,
                    intento,actor_tipo,solicitado_en,recordatorio_programado_en,respuesta_vence_en)
                    VALUES(:id,:claim,:cycle,:attempt,:actor,:now,:now+interval '48 hours',:now+interval '72 hours')'''),
                    {'id':new_choice,'claim':claim_id,'cycle':cycle['solicitud_responsable_en'],
                     'attempt':cycle['intento']+1,'actor':row['actor_tipo'],'now':now})
                s.execute(text('INSERT INTO cancelaciones(id,reclamo_id,proveedor_id,etapa) VALUES(:id,:claim,:provider,:stage)'),
                          {'id':cancellation_id,'claim':claim_id,'provider':selected,'stage':stage})
                if round_row:
                    s.execute(text("UPDATE aari_rondas_presupuesto SET estado='cancelada',cerrada_en=coalesce(cerrada_en,:now) WHERE id=:id"),
                              {'id':round_row['id'],'now':now})
                    self._event(s,round_row['id'],'cancelada',actor=user.id)
                self._invalidate_visit(s,claim_id,cancellation_id)
                s.execute(text('''UPDATE notificaciones SET estado_envio='fallido',proximo_intento_en=NULL,
                    bloqueado_hasta=NULL,ultimo_error='Intento cancelado por el responsable.'
                    WHERE reclamo_id=:claim AND estado_envio IN ('pendiente','procesando') AND
                    (solicitud_tipo_proveedor_id=:choice OR clave_idempotencia LIKE 'aari-quote:%'
                        OR clave_idempotencia LIKE 'hu20:%')'''),{'claim':claim_id,'choice':row['solicitud_id']})
                state=cancellation_graph.invoke({'tipo_gasto':row['tipo_gasto']})['estado_resultante']
                for key,value in (('app.origen_reclamo',user.rol),('app.usuario_reclamo',str(user.id)),
                                  ('app.omitir_notificacion_inquilino','false')):
                    s.execute(text('SELECT set_config(:key,:value,true)'),{'key':key,'value':value})
                s.execute(text('''UPDATE reclamos SET estado=:state,proveedor_seleccionado_id=NULL,
                    presupuesto_seleccionado_id=NULL,monto_seleccionado=NULL WHERE id=:id'''),{'id':claim_id,'state':state})
                saved=s.execute(text('''INSERT INTO reclamo_cancelaciones_coordinacion(id,reclamo_id,request_id,
                    eleccion_id,eleccion_nueva_id,usuario_id,actor_nombre,expected_updated_at,estado_anterior,estado_resultante)
                    VALUES(:id,:claim,:request,:old,:new,:user,:name,:version,:before,:after) RETURNING *'''),
                    {'id':cancellation_id,'claim':claim_id,'request':payload.request_id,'old':row['solicitud_id'],
                     'new':new_choice,'user':user.id,'name':row['nombre_actual'],'version':payload.expected_updated_at,
                     'before':row['estado'],'after':state}).mappings().one()
                if round_row:
                    recipients=s.execute(text('''SELECT DISTINCT p.id,p.email FROM aari_solicitudes_presupuesto q
                        JOIN proveedores p ON p.id=q.proveedor_id JOIN usuarios u ON u.id=p.usuario_id
                        WHERE q.ronda_id=:round AND (CAST(:selected AS uuid) IS NULL OR p.id=CAST(:selected AS uuid))
                          AND p.activo AND u.activo AND NOT u.primer_ingreso AND u.rol='proveedor' AND u.email=p.email'''),
                        {'round':round_row['id'],'selected':str(selected) if selected else None}).mappings().all()
                    for recipient in recipients:
                        self._mail(s,claim_id,'proveedor',recipient['email'],f"hu24:{cancellation_id}:proveedor:{recipient['id']}",
                            'El responsable canceló este intento de coordinación. Su historial se conserva en AARI. '+portal_link('/proveedor'))
                return _result(saved)
        except IntegrityError:
            raise _conflict('La cancelación ya fue registrada. Actualizá antes de reintentar.') from None

    @staticmethod
    def _invalidate_visit(s,claim_id,cancellation_id):
        if not s.execute(text("SELECT to_regclass('public.aari_visita_coordinaciones') IS NOT NULL")).scalar_one():
            return
        ids=s.execute(text('''UPDATE aari_visita_coordinaciones SET etapa='invalidada',version=version+1,
            actualizada_en=clock_timestamp(),revisada_en=clock_timestamp()
            WHERE reclamo_id=:claim AND etapa NOT IN ('confirmada','invalidada') RETURNING id'''),
            {'claim':claim_id}).scalars().all()
        s.execute(text('''UPDATE notificaciones n SET estado_envio='fallido',proximo_intento_en=NULL,
            bloqueado_hasta=NULL,ultimo_error='Coordinación cancelada por el responsable.'
            FROM aari_visita_avisos a JOIN aari_visita_coordinaciones c ON c.id=a.coordinacion_id
            WHERE a.notificacion_id=n.id AND c.reclamo_id=:claim AND c.etapa='invalidada'
              AND n.estado_envio IN ('pendiente','procesando')'''),{'claim':claim_id})
        if conversations_enabled() and ids:
            from app.db.conversations import _append
            for coordination_id in ids:
                threads=s.execute(text('SELECT * FROM aari_conversaciones WHERE coordinacion_visita_id=:id ORDER BY id FOR UPDATE'),
                                  {'id':coordination_id}).mappings().all()
                for thread in threads:
                    _append(s,thread,origin='agente',name='Agente AARI',
                            body='El responsable canceló esta coordinación. El historial se conserva en sólo lectura.',
                            event='hu24:'+str(cancellation_id))
