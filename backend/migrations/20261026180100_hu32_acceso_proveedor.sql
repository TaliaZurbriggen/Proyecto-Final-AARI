-- HU32: aditiva, sin cuentas, correos ni cambios en proveedores legados.
BEGIN;

ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE public.proveedores ADD COLUMN IF NOT EXISTS usuario_id uuid
    REFERENCES public.usuarios(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_proveedores_usuario ON public.proveedores(usuario_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_proveedores_email ON public.proveedores(lower(email));
ALTER TABLE public.proveedores ADD CONSTRAINT chk_proveedor_acceso_email CHECK (
    (email IS NULL OR (email = lower(btrim(email)) AND char_length(email) <= 254
        AND email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'))
    AND (usuario_id IS NULL OR email IS NOT NULL)
);

CREATE TABLE public.proveedor_invitaciones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL UNIQUE,
    proveedor_id uuid NOT NULL REFERENCES public.proveedores(id) ON DELETE RESTRICT,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    email text NOT NULL,
    creado_en timestamptz NOT NULL,
    vence_en timestamptz NOT NULL,
    usado_en timestamptz,
    revocado_en timestamptz,
    envio_estado text NOT NULL DEFAULT 'pendiente'
        CHECK (envio_estado IN ('pendiente', 'enviado', 'fallido')),
    ultimo_error text,
    enviado_en timestamptz,
    CHECK (vence_en > creado_en)
);
CREATE UNIQUE INDEX uq_proveedor_invitacion_vigente
    ON public.proveedor_invitaciones(proveedor_id)
    WHERE usado_en IS NULL AND revocado_en IS NULL;
CREATE INDEX ix_proveedor_invitaciones_historial
    ON public.proveedor_invitaciones(proveedor_id, creado_en DESC);
CREATE INDEX ix_proveedor_invitaciones_usuario
    ON public.proveedor_invitaciones(usuario_id);
ALTER TABLE public.proveedor_invitaciones ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.proveedor_invitaciones FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON public.proveedor_invitaciones FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON public.proveedor_invitaciones FROM authenticated;
    END IF;
END $$;

-- La validación diferida permite crear usuario y vínculo en una transacción,
-- pero impide vincular otro rol o dejar emails/identidades divergentes.
CREATE FUNCTION public.hu32_validar_identidad_proveedor() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'proveedores' THEN
        IF NEW.usuario_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.usuarios u WHERE u.id=NEW.usuario_id
                AND u.rol::text='proveedor' AND u.email=NEW.email
        ) THEN
            RAISE EXCEPTION 'Identidad de proveedor inconsistente' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NEW.rol::text='proveedor' AND NOT EXISTS (
            SELECT 1 FROM public.proveedores p WHERE p.usuario_id=NEW.id AND p.email=NEW.email
        ) THEN
            RAISE EXCEPTION 'Usuario proveedor sin vínculo válido' USING ERRCODE='23514';
        END IF;
        IF EXISTS (SELECT 1 FROM public.proveedores p WHERE p.usuario_id=NEW.id
            AND (NEW.rol::text<>'proveedor' OR p.email<>NEW.email)) THEN
            RAISE EXCEPTION 'Identidad de proveedor inconsistente' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NULL;
END $$;
REVOKE EXECUTE ON FUNCTION public.hu32_validar_identidad_proveedor() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER hu32_proveedor_identidad
    AFTER INSERT OR UPDATE ON public.proveedores DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.hu32_validar_identidad_proveedor();
CREATE CONSTRAINT TRIGGER hu32_usuario_identidad
    AFTER INSERT OR UPDATE ON public.usuarios DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.hu32_validar_identidad_proveedor();
COMMIT;
