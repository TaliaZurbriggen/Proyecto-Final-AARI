"""HU20: selección explícita, auditada e idempotente; ningún envío de red."""

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app.db.quote_portal import SqlAlchemyQuotePortal, REQUEST_SELECT
from app.db.quote_requests import COLUMNS, SOURCE
from app.services.conversations import conversations_enabled
from app.services.quote_portal import QuotePortalError, portal_link
from app.services.quote_requests import request_content
from app.services.external_providers_service import registration_reason


def conflict(message='La selección cambió. Actualizá los presupuestos antes de confirmar.'):
    return QuotePortalError(message, code='selection_conflict')


def selection_result(row, *, repeated=False):
    return {key: (str(row[key]) if key == 'monto' and row[key] is not None else row[key])
            for key in ('id', 'reclamo_id', 'ronda_id', 'modalidad', 'presupuesto_id', 'proveedor_id', 'proveedor_nombre',
                        'monto', 'moneda', 'tipo_importe', 'estado_resultante', 'decidido_en', 'actor_nombre')} | {'repetida': repeated}


class SqlAlchemyQuoteSelections(SqlAlchemyQuotePortal):
    def _access(self, s, claim_id, user, *, lock=False):
        account = s.execute(text('''SELECT rol::text AS rol,activo,primer_ingreso FROM usuarios
            WHERE id=:user FOR SHARE'''), {'user': user.id}).mappings().one_or_none()
        if not account or account['rol'] != user.rol or not account['activo'] or account['primer_ingreso']:
            raise QuotePortalError('La cuenta no está habilitada.', status=403, code='forbidden')
        if user.rol in {'inquilino', 'propietario'}:
            table = 'inquilinos' if user.rol == 'inquilino' else 'propietarios'
            s.execute(text(f'SELECT id FROM {table} WHERE id=:profile AND usuario_id=:user FOR SHARE'),
                      {'profile': user.perfil_id, 'user': user.id}).all()
        s.execute(text('SELECT p.id FROM propiedades p JOIN reclamos r ON r.propiedad_id=p.id '
                       'WHERE r.id=:id FOR SHARE OF p'), {'id': claim_id}).all()
        if lock:
            s.execute(text('SELECT id FROM reclamos WHERE id=:id FOR UPDATE'), {'id': claim_id}).all()
        row = s.execute(text('''SELECT r.id,r.numero,r.descripcion,r.estado,r.updated_at,
            r.operador_asignado_id,ep.id AS eleccion_id,ep.usuario_id AS actor_id,
            rr.actor_tipo,ep.tipo_proveedor,ep.estado AS eleccion_estado,
            r.proveedor_seleccionado_id,r.presupuesto_seleccionado_id,
            i.usuario_id AS tenant_user,i.id AS tenant_id,
            i.estado AS tenant_state,i.propiedad_id AS tenant_property,r.propiedad_id,
            pr.usuario_id AS owner_user,pr.id AS owner_id,
            CASE WHEN rr.actor_tipo='inquilino' THEN i.nombre_completo ELSE pr.nombre_completo END AS actor_nombre
            ''' + SOURCE + ' WHERE r.id=:id'), {'id': claim_id}).mappings().one_or_none()
        responsible = row and user.id == row['actor_id'] and user.rol == row['actor_tipo'] and (
            (user.rol == 'inquilino' and row['tenant_user'] == user.id and row['tenant_id'] == user.perfil_id
             and row['tenant_state'] == 'activo' and row['tenant_property'] == row['propiedad_id'])
            or (user.rol == 'propietario' and row['owner_user'] == user.id and row['owner_id'] == user.perfil_id))
        agency = row and (user.rol == 'administrador' or
                         user.rol == 'operador' and row['operador_asignado_id'] == user.id)
        if not row or not (responsible or agency) or (lock and not responsible):
            raise QuotePortalError('No encontramos ese reclamo.', status=404, code='claim_not_found')
        return row, bool(responsible)

    def _round(self, s, row, *, lock=False):
        return s.execute(text('SELECT * FROM aari_rondas_presupuesto WHERE eleccion_id=:id' +
                              (' FOR UPDATE' if lock else '')), {'id': row['eleccion_id']}).mappings().one_or_none()

    def _valid(self, s, row, round_row):
        current = self._eligible(s, row['id'])
        return (current is not None and round_row is not None and round_row['estado'] in {'esperando', 'disponibles'}
                and current['eleccion_id'] == round_row['eleccion_id']
                and request_content(current)[1] == round_row['huella'])

    @staticmethod
    def _previous(s, choice):
        return s.execute(text('SELECT * FROM reclamo_selecciones_presupuesto WHERE eleccion_id=:id'),
                         {'id': choice}).mappings().one_or_none()

    def get(self, claim_id, user):
        with self.transaction() as s:
            row, responsible = self._access(s, claim_id, user)
            round_row = self._round(s, row)
            previous = self._previous(s, row['eleccion_id'])
            valid = responsible and not previous and self._valid(s, row, round_row)
            now = s.execute(text('SELECT clock_timestamp()')).scalar_one()
            requests = [] if not round_row else s.execute(text(REQUEST_SELECT + ''' WHERE s.ronda_id=:id
                ORDER BY b.moneda NULLS LAST,b.monto NULLS LAST,s.id'''), {'id': round_row['id']}).mappings().all()
            current = self._eligible(s, claim_id) if valid else None
            candidates = set(self._candidates(s, current)) if current else set()
            own_context = current
            if responsible and round_row and own_context is None:
                own_context = s.execute(text('SELECT ' + COLUMNS + SOURCE + ' WHERE r.id=:id'),
                                        {'id': claim_id}).mappings().one_or_none()
            own_current = bool(own_context and round_row and
                               request_content(own_context)[1] == round_row['huella'])
            can_register_own = bool(responsible and not previous and own_current and registration_reason({
                **row, 'ronda_estado': round_row['estado'],
                'presupuestos_disponibles': sum(r['presupuesto_id'] is not None for r in requests),
            }) is None)
            provider_ids = {request['proveedor_id'] for request in requests if request['presupuesto_id']}
            # Una consulta en lote: el número de viajes a la base no crece con las propuestas.
            providers = {} if not provider_ids else {provider['id']: provider for provider in s.execute(text('''
                SELECT p.id,p.activo,p.usuario_id,u.activo AS cuenta_activa,u.primer_ingreso,
                    u.rol::text AS rol,(p.email=u.email) AS correo_vigente,
                    ARRAY(SELECT e.nombre FROM especialidades e JOIN proveedor_especialidades pe
                        ON pe.especialidad_id=e.id WHERE pe.proveedor_id=p.id ORDER BY e.nombre) AS especialidades,
                    coalesce((SELECT jsonb_agg(jsonb_build_object('provincia',c.provincia,'localidad',c.localidad)
                        ORDER BY c.provincia,c.localidad) FROM proveedor_coberturas c WHERE c.proveedor_id=p.id),
                        '[]'::jsonb) AS zonas
                FROM proveedores p LEFT JOIN usuarios u ON u.id=p.usuario_id WHERE p.id IN :ids''')
                .bindparams(bindparam('ids', expanding=True)), {'ids': list(provider_ids)}).mappings()}
            items = []
            for request in requests:
                if request['presupuesto_id'] is None:
                    continue
                provider = providers[request['proveedor_id']]
                enabled = (provider['activo'] and provider['cuenta_activa'] and not provider['primer_ingreso']
                           and provider['rol'] == 'proveedor' and provider['usuario_id'] == request['usuario_id']
                           and provider['correo_vigente'])
                items.append({'id': request['presupuesto_id'], 'solicitud_id': request['id'],
                    'proveedor': request['proveedor_nombre'], 'especialidades': provider['especialidades'],
                    'zonas': provider['zonas'], 'monto': str(request['monto']),
                    'moneda': request['moneda'], 'tipo_importe': request['tipo_importe'],
                    'descripcion': request['trabajo'], 'recibido_en': request['recibido_en'],
                    'puede_elegir': bool(valid and enabled and request['proveedor_id'] in candidates)})
            return {'reclamo_id': claim_id, 'numero': row['numero'], 'descripcion': row['descripcion'],
                'estado': row['estado'], 'updated_at': row['updated_at'],
                'ronda_id': round_row['id'] if round_row else None, 'puede_elegir': bool(valid),
                'puede_cargar_propio': can_register_own,
                'recepcion_abierta': bool(round_row and not round_row['cerrada_en'] and now < round_row['vence_en']),
                'decision': selection_result(previous) if previous else None, 'items': items}

    def choose(self, claim_id, user, payload):
        try:
            with self.transaction() as s:
                row, _ = self._access(s, claim_id, user, lock=True)
                round_row = self._round(s, row, lock=True)
                previous = s.execute(text('SELECT * FROM reclamo_selecciones_presupuesto WHERE request_id=:id'),
                                     {'id': payload.request_id}).mappings().one_or_none()
                if previous:
                    if (previous['reclamo_id'] != claim_id or previous['usuario_id'] != user.id
                        or previous['eleccion_id'] != row['eleccion_id'] or previous['ronda_id'] != payload.ronda_id
                        or previous['modalidad'] != payload.modalidad or previous['presupuesto_id'] != payload.presupuesto_id
                        or previous['expected_updated_at'] != payload.expected_updated_at):
                        raise conflict('El identificador ya fue utilizado para otra selección.')
                    return selection_result(previous, repeated=True)
                if (not self._valid(s, row, round_row) or round_row['id'] != payload.ronda_id
                    or row['updated_at'] != payload.expected_updated_at or self._previous(s, row['eleccion_id'])):
                    raise conflict()
                budget = s.execute(text(REQUEST_SELECT + ' WHERE s.ronda_id=:round AND b.id=:quote'),
                    {'round': round_row['id'], 'quote': payload.presupuesto_id}).mappings().one_or_none()
                if not budget:
                    raise conflict('Ese presupuesto ya no está disponible para este intento.')
                s.execute(text('SELECT id FROM presupuestos WHERE id=:id FOR SHARE'),
                          {'id': payload.presupuesto_id}).scalar_one()
                account = s.execute(text('''SELECT u.id FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id
                    WHERE p.id=:id AND p.activo AND u.id=:user AND u.rol='proveedor'
                    AND u.activo AND NOT u.primer_ingreso AND p.email=u.email FOR SHARE OF p,u'''),
                    {'id': budget['proveedor_id'], 'user': budget['usuario_id']}).scalar_one_or_none()
                if account is None:
                    raise conflict('El proveedor ya no tiene acceso habilitado.')
                # Releer después de los bloqueos: nunca persistir un importe/contexto anterior.
                budget = s.execute(text(REQUEST_SELECT + ' WHERE s.ronda_id=:round AND b.id=:quote'),
                    {'round': round_row['id'], 'quote': payload.presupuesto_id}).mappings().one()
                if not self._current(s, budget):
                    raise conflict('Ese presupuesto ya no está disponible para este intento.')
                state = 'Proveedor seleccionado'
                for setting, value in (('app.origen_reclamo', user.rol), ('app.usuario_reclamo', str(user.id)),
                                       ('app.omitir_notificacion_inquilino', 'false')):
                    s.execute(text('SELECT set_config(:key,:value,true)'), {'key': setting, 'value': value})
                s.execute(text('''UPDATE reclamos SET estado=:state,proveedor_seleccionado_id=:provider,
                    presupuesto_seleccionado_id=:quote,monto_seleccionado=:amount WHERE id=:id'''),
                    {'id': claim_id, 'state': state, 'provider': budget['proveedor_id'],
                     'quote': payload.presupuesto_id, 'amount': budget['monto']})
                history = s.execute(text('''SELECT id FROM reclamo_historial_estados WHERE reclamo_id=:id
                    AND estado_nuevo=:state AND usuario_id=:user ORDER BY timestamp DESC,id DESC LIMIT 1'''),
                    {'id': claim_id, 'state': state, 'user': user.id}).scalar_one()
                saved = s.execute(text('''INSERT INTO reclamo_selecciones_presupuesto
                    (reclamo_id,eleccion_id,ronda_id,request_id,expected_updated_at,usuario_id,actor_nombre,
                     modalidad,presupuesto_id,proveedor_id,proveedor_nombre,monto,moneda,tipo_importe,estado_resultante,historial_estado_id)
                    VALUES (:claim,:choice,:round,:request,:expected,:user,:name,:kind,:quote,:provider,:provider_name,
                        :amount,:currency,:price_kind,:state,:history) RETURNING *'''),
                    {'claim': claim_id, 'choice': row['eleccion_id'], 'round': round_row['id'],
                     'request': payload.request_id, 'expected': payload.expected_updated_at, 'user': user.id,
                     'name': row['actor_nombre'], 'kind': payload.modalidad, 'quote': payload.presupuesto_id,
                     'provider': budget['proveedor_id'], 'amount': budget['monto'],
                     'provider_name': budget['proveedor_nombre'],
                     'currency': budget['moneda'], 'price_kind': budget['tipo_importe'],
                     'state': state, 'history': history}).mappings().one()
                s.execute(text('''UPDATE aari_rondas_presupuesto SET cerrada_en=coalesce(cerrada_en,clock_timestamp()),
                    estado='disponibles' WHERE id=:id'''), {'id': round_row['id']})
                message = ('El responsable seleccionó tu presupuesto. La fecha de visita todavía debe coordinarse. '
                           'Un importe mínimo no es un precio final ni un máximo autorizado. ')
                email = s.execute(text('SELECT email FROM proveedores WHERE id=:id'),
                                  {'id': budget['proveedor_id']}).scalar_one()
                self._mail(s, claim_id, 'proveedor', email, f"hu20:{saved['id']}:seleccion",
                           message + portal_link('/proveedor/solicitudes/' + str(budget['id'])))
                if conversations_enabled():
                    from app.db.conversations import CONTEXT, _ensure, _append
                    context = s.execute(text(CONTEXT), {'id': budget['id']}).mappings().one()
                    _ensure(s, context)
                    threads = s.execute(text("SELECT * FROM aari_conversaciones WHERE solicitud_id=:id AND finalidad='presupuesto' ORDER BY id FOR UPDATE"),
                                        {'id': budget['id']}).mappings().all()
                    for thread in threads:
                        _append(s, thread, origin='agente', name='Agente AARI',
                                body='El responsable confirmó la selección de este presupuesto. La visita aún no está programada.',
                                event='hu20:' + str(saved['id']))
                # No sobrescribir HU17 ni inventar el contacto o la derivación HU18.
                return selection_result(saved)
        except IntegrityError:
            raise conflict('La selección ya fue registrada. Actualizá antes de reintentar.') from None
