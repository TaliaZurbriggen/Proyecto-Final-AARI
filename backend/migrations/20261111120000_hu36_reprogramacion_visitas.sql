BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.aari_visita_coordinaciones ADD COLUMN version_horario integer NOT NULL DEFAULT 0
    CHECK (version_horario >= 0);

CREATE TABLE public.aari_visita_reprogramaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coordinacion_id uuid NOT NULL REFERENCES public.aari_visita_coordinaciones(id),
    version_horario integer NOT NULL CHECK (version_horario >= 0),
    fecha_anterior timestamptz NOT NULL,
    fecha_propuesta timestamptz NOT NULL,
    solicitante_id uuid NOT NULL REFERENCES public.usuarios(id),
    solicitante_rol text NOT NULL CHECK (solicitante_rol IN ('inquilino', 'proveedor')),
    motivo text NOT NULL CHECK (char_length(btrim(motivo)) BETWEEN 1 AND 500),
    creada_en timestamptz NOT NULL,
    vence_en timestamptz NOT NULL,
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'aceptada', 'rechazada', 'retirada', 'vencida')),
    decidida_en timestamptz,
    decision_usuario_id uuid REFERENCES public.usuarios(id),
    decision_rol text CHECK (decision_rol IN ('inquilino', 'proveedor')),
    CHECK (fecha_propuesta <> fecha_anterior AND vence_en > creada_en
        AND vence_en <= least(fecha_propuesta, fecha_anterior, creada_en + interval '24 hours')),
    CHECK ((estado = 'pendiente' AND decidida_en IS NULL AND decision_usuario_id IS NULL AND decision_rol IS NULL)
        OR (estado = 'vencida' AND decidida_en IS NOT NULL AND decidida_en = vence_en
            AND decision_usuario_id IS NULL AND decision_rol IS NULL)
        OR (estado IN ('aceptada', 'rechazada', 'retirada') AND decidida_en IS NOT NULL
            AND decidida_en >= creada_en AND decidida_en < vence_en
            AND decision_usuario_id IS NOT NULL AND decision_rol IS NOT NULL
            AND (decision_usuario_id = solicitante_id) = (estado = 'retirada')
            AND (decision_rol = solicitante_rol) = (estado = 'retirada')))
);
CREATE UNIQUE INDEX uq_visita_reprogramacion_pendiente ON public.aari_visita_reprogramaciones(coordinacion_id)
    WHERE estado = 'pendiente';
CREATE INDEX idx_visita_reprogramaciones ON public.aari_visita_reprogramaciones(coordinacion_id, creada_en, id);

CREATE TABLE public.aari_visita_ausencias (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coordinacion_id uuid NOT NULL REFERENCES public.aari_visita_coordinaciones(id),
    version_horario integer NOT NULL CHECK (version_horario >= 0),
    fecha_visita timestamptz NOT NULL,
    autor_id uuid NOT NULL REFERENCES public.usuarios(id),
    autor_rol text NOT NULL CHECK (autor_rol IN ('inquilino', 'proveedor')),
    tipo text NOT NULL CHECK (tipo IN ('no_realizada', 'contraparte_ausente')),
    observaciones text NOT NULL CHECK (char_length(btrim(observaciones)) BETWEEN 1 AND 500),
    creada_en timestamptz NOT NULL CHECK (creada_en >= fecha_visita),
    UNIQUE (coordinacion_id, version_horario, autor_id)
);

ALTER TABLE public.aari_visita_reprogramaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_visita_ausencias ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aari_visita_reprogramaciones, public.aari_visita_ausencias FROM PUBLIC, anon, authenticated;
CREATE TRIGGER aari_visita_ausencia_inmutable BEFORE UPDATE OR DELETE ON public.aari_visita_ausencias
    FOR EACH ROW EXECUTE FUNCTION public.aari_conversacion_mensaje_inmutable();

COMMIT;
