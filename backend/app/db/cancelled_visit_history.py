"""HU24: lectura histórica de visitas canceladas sin reactivar HU23.

Reutiliza identidad, contexto, paginación y lecturas HU33. No requiere importar
HU23 ni una selección actual: el vínculo procede de la auditoría de cancelación.
"""

import os
from sqlalchemy import text
from app.services.conversations import ConversationError


def available(session):
    return session.bind.dialect.name=='postgresql' and session.execute(text('''SELECT
        to_regclass('public.reclamo_cancelaciones_coordinacion') IS NOT NULL
        AND to_regclass('public.aari_visita_coordinaciones') IS NOT NULL''')).scalar_one()


ORIGIN=''' FROM aari_conversaciones t JOIN aari_visita_coordinaciones v ON v.id=t.coordinacion_visita_id
    JOIN aari_solicitudes_presupuesto q ON q.id=v.solicitud_id AND q.reclamo_id=v.reclamo_id
    JOIN aari_rondas_presupuesto rp ON rp.id=q.ronda_id
    JOIN reclamo_cancelaciones_coordinacion a ON a.reclamo_id=v.reclamo_id AND a.eleccion_id=rp.eleccion_id'''


class CancelledVisitHistory:
    def __init__(self,conversations):
        self.repo=conversations

    def _scope(self,session,thread_id,user):
        if not available(session): return None
        row=session.execute(text('''SELECT t.*,v.reclamo_id,v.solicitud_id AS original_request,
            v.inquilino_id,v.inquilino_usuario_id,v.proveedor_id,v.proveedor_usuario_id,
            v.responsable_usuario_id'''+ORIGIN+" WHERE t.id=:id AND v.etapa='invalidada'"),
            {'id':thread_id}).mappings().one_or_none()
        if not row: return None
        context,_,roles=self.repo._context(session,row['original_request'],user)
        tenant=(roles['tenant'] and user.id==row['inquilino_usuario_id'] and user.perfil_id==row['inquilino_id'])
        provider=(roles['provider'] and user.id==row['proveedor_usuario_id'] and user.perfil_id==row['proveedor_id'])
        responsible=(roles['responsible'] and user.id==row['responsable_usuario_id'])
        if responsible and user.rol=='propietario':
            responsible=session.execute(text('SELECT EXISTS(SELECT 1 FROM propietarios WHERE id=:profile AND usuario_id=:user)'),
                                        {'profile':user.perfil_id,'user':user.id}).scalar_one()
        allowed=(roles['agency'] or row['audiencia']=='inquilino' and (tenant or provider)
                 or row['audiencia']=='responsable' and responsible)
        if not allowed:
            raise ConversationError('No encontramos esa conversación.',status=404,code='conversation_not_found')
        # Releer la etapa bajo el bloqueo del reclamo adquirido por _context.
        thread=session.execute(text('SELECT * FROM aari_conversaciones WHERE id=:id FOR UPDATE'),
                               {'id':thread_id}).mappings().one()
        return thread,context,roles

    def messages(self,thread_id,user,*,before=None,after=None,limit=30):
        if before is not None and after is not None:
            raise ConversationError('Usá un solo sentido de paginación.',status=422,code='invalid_cursor')
        with self.repo.transaction() as session:
            scope=self._scope(session,thread_id,user)
            if scope is None: return None
            thread,context,roles=scope
            direction='ASC' if after is not None else 'DESC'
            bound=' AND numero>:cursor' if after is not None else ' AND numero<:cursor' if before is not None else ''
            rows=session.execute(text('''SELECT id,numero,origen,autor_id,autor_nombre,texto,creado_en
                FROM aari_conversacion_mensajes WHERE conversacion_id=:id'''+bound+
                ' ORDER BY numero '+direction+' LIMIT :limit'),
                {'id':thread_id,'cursor':after if after is not None else before,'limit':limit+1}).mappings().all()
            more,rows=len(rows)>limit,rows[:limit]
            if after is None: rows=rows[::-1]
            read,unread=self.repo._reader(session,thread,user.id,audit=roles['agency'])
            return {'id':thread_id,'solicitud_id':None,'reclamo_id':context['reclamo_id'],
                'finalidad':'coordinacion','numero_reclamo':context['numero'],'puede_enviar':False,
                'motivo_solo_lectura':'Este intento fue cancelado. El historial se conserva en sólo lectura.',
                'puede_finalizar':False,'coordinacion_url':None,'ultimo_numero':thread['ultimo_numero'],
                'leido_hasta':read,'no_leidos':unread,'hay_anteriores':more if after is None else False,
                'hay_nuevos':more if after is not None else False,
                'items':[self.repo._message(row,user.id) for row in rows]}

    def read(self,thread_id,user,through):
        with self.repo.transaction() as session:
            scope=self._scope(session,thread_id,user)
            if scope is None: return None
            thread,_,roles=scope
            if through>thread['ultimo_numero']:
                raise ConversationError('No se pueden marcar mensajes futuros como leídos.',status=422,code='invalid_read_position')
            last=session.execute(text('''INSERT INTO aari_conversacion_lecturas(conversacion_id,usuario_id,ultimo_numero)
                VALUES(:id,:user,:through) ON CONFLICT(conversacion_id,usuario_id) DO UPDATE SET
                ultimo_numero=greatest(aari_conversacion_lecturas.ultimo_numero,excluded.ultimo_numero)
                RETURNING ultimo_numero'''),{'id':thread_id,'user':user.id,'through':through}).scalar_one()
            return {'leido_hasta':last,'no_leidos':self.repo._reader(session,thread,user.id,audit=roles['agency'])[1]}

    def reject_write(self,thread_id,user):
        with self.repo.transaction() as session:
            if self._scope(session,thread_id,user) is not None:
                raise ConversationError('El intento está cancelado. El historial es de sólo lectura.',status=403,code='conversation_read_only')


def inbox_select(session,user,*,has_visit_reader):
    if not available(session): return None
    scopes={
        'inquilino':"t.audiencia='inquilino' AND v.inquilino_usuario_id=:user AND i.usuario_id=:user AND i.id=:profile AND i.estado='activo' AND i.propiedad_id=r.propiedad_id AND r.inquilino_id=i.id",
        'proveedor':"t.audiencia='inquilino' AND v.proveedor_usuario_id=:user AND p.usuario_id=:user AND p.id=:profile AND p.activo",
        'propietario':"t.audiencia='responsable' AND v.responsable_usuario_id=:user AND owner.usuario_id=:user AND owner.id=:profile",
        'administrador':'true','operador':'r.operador_asignado_id=:user',
    }
    # HU23 ya incluye su última coordinación. Agregar sólo las canceladas
    # anteriores en ese caso; si está apagada/ausente, conservar también esa última.
    visit_inbox=has_visit_reader and os.getenv('AARI_VISITS_ENABLED','false').lower() in {'1','true','yes'}
    older=" AND v.id<>(SELECT x.id FROM aari_visita_coordinaciones x WHERE x.reclamo_id=r.id ORDER BY x.creada_en DESC,x.id DESC LIMIT 1)" if visit_inbox else ''
    return '''SELECT t.id,t.solicitud_id,t.finalidad,t.audiencia,r.numero,p.nombre_razon_social AS proveedor,
        t.actualizada_en,t.consultas_cerradas_en,CASE WHEN :audit THEN 0 ELSE
        (SELECT count(*) FROM aari_conversacion_mensajes m WHERE m.conversacion_id=t.id
            AND m.numero>coalesce(l.ultimo_numero,0) AND m.autor_id IS DISTINCT FROM :user) END AS no_leidos'''+ORIGIN+'''
        JOIN reclamos r ON r.id=v.reclamo_id JOIN inquilinos i ON i.id=v.inquilino_id
        JOIN propiedades property ON property.id=r.propiedad_id JOIN propietarios owner ON owner.id=property.propietario_id
        JOIN proveedores p ON p.id=v.proveedor_id
        LEFT JOIN aari_conversacion_lecturas l ON l.conversacion_id=t.id AND l.usuario_id=:user
        WHERE v.etapa='invalidada' AND ('''+scopes.get(user.rol,'false')+')'+older
