-- HU23. Aditiva; no inicia coordinaciones, workers ni envíos al aplicar.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
CREATE TABLE public.aari_visita_coordinaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reclamo_id uuid NOT NULL REFERENCES public.reclamos(id),
    presupuesto_id uuid NOT NULL REFERENCES public.presupuestos(id),
    proveedor_id uuid NOT NULL REFERENCES public.proveedores(id),
    solicitud_id uuid NOT NULL REFERENCES public.aari_solicitudes_presupuesto(id),
    inquilino_id uuid NOT NULL REFERENCES public.inquilinos(id),
    inquilino_usuario_id uuid NOT NULL REFERENCES public.usuarios(id),
    proveedor_usuario_id uuid NOT NULL REFERENCES public.usuarios(id),
    responsable_usuario_id uuid NOT NULL REFERENCES public.usuarios(id),
    contexto jsonb NOT NULL,
    seleccion_version timestamptz NOT NULL,
    etapa text NOT NULL DEFAULT 'esperando_disponibilidad' CHECK (etapa IN
        ('esperando_disponibilidad','esperando_confirmacion','negociando','confirmada','sin_acuerdo','invalidada')),
    version integer NOT NULL DEFAULT 0 CHECK (version >= 0),
    vence_en timestamptz,
    propuesta_fecha timestamptz,
    propuesta_autor_id uuid REFERENCES public.usuarios(id),
    propuesta_version integer,
    visita_id uuid UNIQUE REFERENCES public.visitas(id),
    creada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    actualizada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    revisada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((propuesta_fecha IS NULL AND propuesta_autor_id IS NULL AND propuesta_version IS NULL)
        OR (propuesta_fecha IS NOT NULL AND propuesta_autor_id IS NOT NULL AND propuesta_version IS NOT NULL)),
    CHECK (etapa<>'confirmada' OR visita_id IS NOT NULL)
);
CREATE UNIQUE INDEX uq_visita_coordinacion_activa ON public.aari_visita_coordinaciones(reclamo_id)
    WHERE etapa IN ('esperando_disponibilidad','esperando_confirmacion','negociando','confirmada');
CREATE UNIQUE INDEX uq_visita_coordinacion_seleccion ON public.aari_visita_coordinaciones(reclamo_id,presupuesto_id,seleccion_version);
CREATE INDEX idx_visita_coordinacion_presupuesto ON public.aari_visita_coordinaciones(presupuesto_id);
CREATE INDEX idx_visita_coordinacion_proveedor ON public.aari_visita_coordinaciones(proveedor_id);
CREATE INDEX idx_visita_coordinacion_solicitud ON public.aari_visita_coordinaciones(solicitud_id);
CREATE INDEX idx_visita_coordinacion_inquilino ON public.aari_visita_coordinaciones(inquilino_id);
CREATE INDEX idx_visita_coordinacion_participantes ON public.aari_visita_coordinaciones(inquilino_usuario_id,proveedor_usuario_id);
CREATE INDEX idx_visita_coordinacion_responsable ON public.aari_visita_coordinaciones(responsable_usuario_id);
CREATE INDEX idx_visita_coordinacion_vencimiento ON public.aari_visita_coordinaciones(vence_en)
    WHERE etapa IN ('esperando_confirmacion','negociando');
CREATE INDEX idx_visita_coordinacion_revision ON public.aari_visita_coordinaciones(revisada_en,id);
CREATE TABLE public.aari_visita_opciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coordinacion_id uuid NOT NULL REFERENCES public.aari_visita_coordinaciones(id),
    desde timestamptz NOT NULL,
    hasta timestamptz NOT NULL,
    CHECK (desde < hasta),
    UNIQUE(coordinacion_id,desde)
);
CREATE TABLE public.aari_visita_acciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coordinacion_id uuid NOT NULL REFERENCES public.aari_visita_coordinaciones(id),
    request_id uuid NOT NULL,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id),
    accion text NOT NULL,
    datos jsonb NOT NULL,
    huella text NOT NULL,
    version integer NOT NULL,
    creada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(coordinacion_id,request_id)
);
CREATE INDEX idx_visita_accion_usuario ON public.aari_visita_acciones(usuario_id);
CREATE TABLE public.aari_visita_avisos (
    notificacion_id uuid PRIMARY KEY REFERENCES public.notificaciones(id),
    coordinacion_id uuid NOT NULL REFERENCES public.aari_visita_coordinaciones(id),
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id),
    evento text NOT NULL,
    UNIQUE(coordinacion_id,usuario_id,evento)
);
CREATE INDEX idx_visita_aviso_usuario ON public.aari_visita_avisos(usuario_id);
-- Los hilos nuevos pertenecen a una coordinación, nunca a una solicitud falsa.
ALTER TABLE public.aari_conversaciones ADD COLUMN coordinacion_visita_id uuid
    REFERENCES public.aari_visita_coordinaciones(id);
ALTER TABLE public.aari_conversaciones ALTER COLUMN solicitud_id DROP NOT NULL;
ALTER TABLE public.aari_conversaciones ADD CONSTRAINT chk_hilo_visita_origen CHECK (
    (solicitud_id IS NOT NULL AND coordinacion_visita_id IS NULL)
    OR (solicitud_id IS NULL AND coordinacion_visita_id IS NOT NULL AND finalidad='coordinacion'));
CREATE UNIQUE INDEX uq_hilo_visita_audiencia ON public.aari_conversaciones(coordinacion_visita_id,audiencia)
    WHERE coordinacion_visita_id IS NOT NULL;
ALTER TABLE public.visitas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.visitas FROM PUBLIC,anon,authenticated;
ALTER TABLE public.aari_visita_coordinaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_visita_opciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_visita_acciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_visita_avisos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aari_visita_coordinaciones,public.aari_visita_opciones,
    public.aari_visita_acciones,public.aari_visita_avisos FROM PUBLIC,anon,authenticated;
CREATE TRIGGER aari_visita_accion_inmutable BEFORE UPDATE OR DELETE ON public.aari_visita_acciones
    FOR EACH ROW EXECUTE FUNCTION public.aari_conversacion_mensaje_inmutable();
-- Se reutiliza un tipo genérico permitido; el vínculo estructurado identifica HU23.
COMMIT;
