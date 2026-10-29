-- HU33: canal privado por solicitud/intento/finalidad. No activa workers ni envíos.
BEGIN;
CREATE TABLE public.aari_conversaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    solicitud_id uuid NOT NULL REFERENCES public.aari_solicitudes_presupuesto(id) ON DELETE RESTRICT,
    finalidad text NOT NULL CHECK (finalidad IN ('presupuesto', 'consulta_tecnica', 'coordinacion')),
    audiencia text NOT NULL CHECK (audiencia IN ('proveedor', 'responsable', 'inquilino')),
    participante_usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    responsable_usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    ultimo_numero bigint NOT NULL DEFAULT 0 CHECK (ultimo_numero >= 0),
    creada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    actualizada_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    apertura_request_id uuid,
    cierre_request_id uuid,
    consultas_abiertas_en timestamptz,
    consultas_cerradas_en timestamptz,
    UNIQUE(solicitud_id, finalidad, audiencia),
    CHECK ((finalidad='consulta_tecnica' AND audiencia='inquilino'
        AND apertura_request_id IS NOT NULL AND consultas_abiertas_en IS NOT NULL)
        OR (finalidad IN ('presupuesto','coordinacion') AND consultas_abiertas_en IS NULL)),
    CHECK ((consultas_cerradas_en IS NULL AND cierre_request_id IS NULL)
        OR (consultas_cerradas_en IS NOT NULL AND cierre_request_id IS NOT NULL))
);
CREATE TABLE public.aari_conversacion_mensajes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversacion_id uuid NOT NULL REFERENCES public.aari_conversaciones(id) ON DELETE RESTRICT,
    numero bigint NOT NULL CHECK (numero > 0),
    origen text NOT NULL CHECK (origen IN ('humano', 'agente')),
    autor_id uuid REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    autor_nombre text NOT NULL,
    texto text NOT NULL CHECK (length(btrim(texto)) BETWEEN 1 AND 2000),
    request_id uuid,
    clave_evento text,
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(conversacion_id, numero),
    UNIQUE(conversacion_id, autor_id, request_id),
    UNIQUE(conversacion_id, clave_evento),
    CHECK ((origen = 'humano' AND autor_id IS NOT NULL AND request_id IS NOT NULL AND clave_evento IS NULL)
        OR (origen = 'agente' AND autor_id IS NULL AND request_id IS NULL AND clave_evento IS NOT NULL))
);
CREATE TABLE public.aari_conversacion_lecturas (
    conversacion_id uuid NOT NULL REFERENCES public.aari_conversaciones(id) ON DELETE RESTRICT,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    ultimo_numero bigint NOT NULL CHECK (ultimo_numero >= 0),
    leida_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(conversacion_id, usuario_id)
);
CREATE INDEX idx_conversacion_responsable ON public.aari_conversaciones(responsable_usuario_id);
CREATE INDEX idx_conversacion_participante ON public.aari_conversaciones(participante_usuario_id);
CREATE INDEX idx_conversacion_mensaje_autor ON public.aari_conversacion_mensajes(autor_id);
CREATE INDEX idx_conversacion_lectura_usuario ON public.aari_conversacion_lecturas(usuario_id);
CREATE FUNCTION public.aari_conversacion_mensaje_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El historial de conversación no admite edición ni eliminación.';
END;
$$;
CREATE TRIGGER aari_mensaje_inmutable BEFORE UPDATE OR DELETE
ON public.aari_conversacion_mensajes FOR EACH ROW
EXECUTE FUNCTION public.aari_conversacion_mensaje_inmutable();
ALTER TABLE public.aari_conversaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_conversacion_mensajes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_conversacion_lecturas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aari_conversaciones, public.aari_conversacion_mensajes,
    public.aari_conversacion_lecturas FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.aari_conversacion_mensaje_inmutable() FROM PUBLIC, anon, authenticated;
COMMIT;
