"""AARI-345: hechos durables de los módulos, sin contactos ni texto de mensajes.

Las tablas opcionales permiten conservar el despliegue incremental de HU21.
Nunca confundir una ronda o una visita de un intento anterior con el vigente.
"""

from app.db.current_provider_choice import CURRENT_CHOICE


def workflow_context(conn, row):
    installed = conn.execute("""SELECT
        to_regclass('public.reclamo_elecciones_proveedor') IS NOT NULL AS choices,
        to_regclass('public.aari_rondas_presupuesto') IS NOT NULL AS rounds,
        to_regclass('public.reclamo_selecciones_presupuesto') IS NOT NULL AS selections,
        EXISTS(SELECT 1 FROM pg_attribute
            WHERE attrelid=to_regclass('public.aari_visita_coordinaciones')
              AND attname='seleccion_id' AND NOT attisdropped) AS visits""").fetchone()
    if not installed['choices']:
        return {}
    choice = conn.execute("""SELECT ep.id,ep.estado,ep.respuesta_vence_en
        FROM public.reclamo_elecciones_proveedor ep
        JOIN public.reclamo_responsables rr ON rr.reclamo_id=ep.reclamo_id
            AND rr.solicitado_en=ep.solicitud_responsable_en AND rr.actor_tipo=ep.actor_tipo
        WHERE ep.reclamo_id=%s AND """ + CURRENT_CHOICE, (row['id'],)).fetchone()
    if not choice:
        return {}
    result = {'eleccion_id': choice['id']}
    if not installed['rounds']:
        return result
    round_row = conn.execute("""SELECT id,estado,vence_en,cerrada_en
        FROM public.aari_rondas_presupuesto WHERE eleccion_id=%s""",
        (choice['id'],)).fetchone()
    if not round_row:
        return result
    result.update(ronda_id=round_row['id'], estado_ronda=round_row['estado'])
    if row['estado'] == 'Pendiente de asignación' and not round_row['cerrada_en']:
        result['plazo_modulo'] = round_row['vence_en']
    if not installed['selections']:
        return result
    selection = conn.execute("""SELECT id FROM public.reclamo_selecciones_presupuesto
        WHERE reclamo_id=%s AND eleccion_id=%s AND ronda_id=%s
          AND presupuesto_id=%s AND proveedor_id=%s AND monto=%s
          AND modalidad='fidelizado'""", (row['id'], choice['id'], round_row['id'],
        row['presupuesto_seleccionado_id'], row['proveedor_seleccionado_id'],
        row['monto_seleccionado'])).fetchone()
    if not selection:
        return result
    result['seleccion_id'] = selection['id']
    if installed['visits']:
        visit = conn.execute("""SELECT id,etapa,version,vence_en
            FROM public.aari_visita_coordinaciones
            WHERE reclamo_id=%s AND seleccion_id=%s
            ORDER BY creada_en DESC,id DESC LIMIT 1""",
            (row['id'], selection['id'])).fetchone()
        if visit:
            result.update(coordinacion_visita_id=visit['id'], etapa_visita=visit['etapa'],
                          version_visita=visit['version'])
            if visit['etapa'] in {'esperando_confirmacion', 'negociando'}:
                result['plazo_modulo'] = visit['vence_en']
    return result
