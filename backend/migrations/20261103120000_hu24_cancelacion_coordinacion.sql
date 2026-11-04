-- HU24. Migración nueva; no habilita workers ni envía correos.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Mantener decisiones anteriores: una solicitud nueva por intento, no UPDATE
-- de la elección histórica ni cambios al ciclo/autorización del responsable.
ALTER TABLE public.reclamo_elecciones_proveedor ADD COLUMN intento integer NOT NULL DEFAULT 0 CHECK(intento>=0);
ALTER TABLE public.reclamo_elecciones_proveedor DROP CONSTRAINT uq_eleccion_solicitud;
ALTER TABLE public.reclamo_elecciones_proveedor ADD CONSTRAINT uq_eleccion_solicitud
    UNIQUE(reclamo_id,solicitud_responsable_en,intento);
CREATE INDEX idx_eleccion_actual ON public.reclamo_elecciones_proveedor
    (reclamo_id,solicitud_responsable_en,solicitado_en DESC,id DESC);

-- La apertura original siempre usa intento=0. Adaptar sólo el arbitraje de
-- duplicados del trigger HU17, preservando su lógica y sus permisos.
DO $migration$
DECLARE
    definition text := pg_catalog.pg_get_functiondef('public.abrir_eleccion_proveedor()'::regprocedure);
    marker text := 'on conflict (reclamo_id,solicitud_responsable_en) do nothing';
BEGIN
    IF pg_catalog.strpos(definition,marker)=0 THEN
        RAISE EXCEPTION 'La apertura HU17 difiere de la base. Revisar antes de migrar.';
    END IF;
    EXECUTE pg_catalog.replace(definition,marker,'on conflict do nothing');
END;
$migration$;

ALTER TABLE public.cancelaciones ADD CONSTRAINT uq_cancelacion_id_reclamo UNIQUE(id,reclamo_id);
CREATE TABLE public.reclamo_cancelaciones_coordinacion (
    id uuid PRIMARY KEY,
    reclamo_id uuid NOT NULL REFERENCES public.reclamos(id) ON DELETE RESTRICT,
    request_id uuid NOT NULL UNIQUE,
    eleccion_id uuid NOT NULL UNIQUE,
    eleccion_nueva_id uuid NOT NULL UNIQUE,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    actor_nombre text NOT NULL,
    expected_updated_at timestamptz NOT NULL,
    estado_anterior text NOT NULL,
    estado_resultante text NOT NULL CHECK(estado_resultante IN ('Autorizado','Pendiente de respuesta del responsable')),
    creada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY(id,reclamo_id) REFERENCES public.cancelaciones(id,reclamo_id) ON DELETE RESTRICT,
    FOREIGN KEY(eleccion_id,reclamo_id) REFERENCES public.reclamo_elecciones_proveedor(id,reclamo_id),
    FOREIGN KEY(eleccion_nueva_id,reclamo_id) REFERENCES public.reclamo_elecciones_proveedor(id,reclamo_id),
    CHECK(eleccion_id<>eleccion_nueva_id)
);
CREATE INDEX idx_cancelacion_usuario ON public.reclamo_cancelaciones_coordinacion(usuario_id);
CREATE INDEX idx_cancelacion_historia ON public.reclamo_cancelaciones_coordinacion(reclamo_id,creada_en DESC,id DESC);
CREATE INDEX idx_cancelacion_nueva_eleccion ON public.reclamo_cancelaciones_coordinacion(eleccion_nueva_id,reclamo_id);
CREATE INDEX idx_cancelacion_eleccion ON public.reclamo_cancelaciones_coordinacion(eleccion_id,reclamo_id);
ALTER TABLE public.cancelaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reclamo_cancelaciones_coordinacion ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.cancelaciones,public.reclamo_cancelaciones_coordinacion FROM PUBLIC,anon,authenticated;

CREATE FUNCTION public.hu24_cancelacion_inmutable() RETURNS trigger LANGUAGE plpgsql
SET search_path='' AS $$ BEGIN RAISE EXCEPTION 'El historial de cancelación es inmutable.'; END; $$;
REVOKE ALL ON FUNCTION public.hu24_cancelacion_inmutable() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER hu24_auditoria_inmutable BEFORE UPDATE OR DELETE ON public.reclamo_cancelaciones_coordinacion
    FOR EACH ROW EXECUTE FUNCTION public.hu24_cancelacion_inmutable();

-- Sustituir el destinatario ficticio del trigger inicial por una cuenta
-- operativa real. Un replay no inserta cancelaciones ni duplica esta alerta.
CREATE OR REPLACE FUNCTION public.chk_alerta_cancelaciones() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE recipient record;
BEGIN
    IF (SELECT count(*) FROM public.cancelaciones WHERE reclamo_id=NEW.reclamo_id)>=3 THEN
        SELECT u.email,u.rol::text AS rol,r.estado INTO recipient FROM public.usuarios u
        JOIN public.reclamos r ON r.id=NEW.reclamo_id
        WHERE u.activo AND NOT u.primer_ingreso AND u.rol::text IN ('operador','administrador')
        ORDER BY (u.id=r.operador_asignado_id) DESC NULLS LAST,
                 (u.rol::text='administrador') DESC,u.id LIMIT 1;
        IF recipient.email IS NOT NULL THEN
            INSERT INTO public.notificaciones(reclamo_id,destinatario_tipo,destinatario_contacto,
                canal,asunto,mensaje,estado_reclamo,tipo_evento,clave_idempotencia,estado_envio,proximo_intento_en)
            VALUES(NEW.reclamo_id,recipient.rol,recipient.email,'email','AARI - Cancelaciones de coordinación',
                'El reclamo acumula tres o más cancelaciones. Revisá su historial en AARI.',
                recipient.estado,'alerta_operador','hu24:'||NEW.id::text||':alerta','pendiente',clock_timestamp())
            ON CONFLICT(clave_idempotencia) WHERE clave_idempotencia IS NOT NULL DO NOTHING;
        END IF;
    END IF;
    RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION public.chk_alerta_cancelaciones() FROM PUBLIC,anon,authenticated;
COMMIT;
