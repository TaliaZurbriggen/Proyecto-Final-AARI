-- HU18: amplía la tabla existente sin atribuir autor/elección a registros históricos.
-- Requiere HU17 y HU19 AARI. No aplicar a Supabase sin autorización.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

ALTER TABLE public.proveedores_externos
    ADD COLUMN eleccion_id uuid,
    ADD COLUMN usuario_id uuid REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    ADD COLUMN actor_nombre text,
    ADD COLUMN request_id uuid,
    ADD COLUMN expected_updated_at timestamptz,
    ADD COLUMN historial_estado_id uuid REFERENCES public.reclamo_historial_estados(id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_externo_eleccion FOREIGN KEY(eleccion_id,reclamo_id)
        REFERENCES public.reclamo_elecciones_proveedor(id,reclamo_id) ON DELETE RESTRICT,
    ADD CONSTRAINT chk_externo_auditoria CHECK (
        (eleccion_id IS NULL AND usuario_id IS NULL AND actor_nombre IS NULL AND request_id IS NULL
         AND expected_updated_at IS NULL AND historial_estado_id IS NULL)
        OR (eleccion_id IS NOT NULL AND usuario_id IS NOT NULL AND actor_nombre IS NOT NULL AND request_id IS NOT NULL
            AND expected_updated_at IS NOT NULL AND historial_estado_id IS NOT NULL
            AND length(btrim(actor_nombre))>0 AND length(nombre) BETWEEN 3 AND 120
            AND nombre ~ '[[:alpha:]]' AND nombre !~ '[0-9]' AND nombre=btrim(nombre)));

CREATE UNIQUE INDEX uq_externo_eleccion ON public.proveedores_externos(eleccion_id) WHERE eleccion_id IS NOT NULL;
CREATE UNIQUE INDEX uq_externo_request ON public.proveedores_externos(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX idx_externo_usuario ON public.proveedores_externos(usuario_id);
CREATE INDEX idx_externo_historial ON public.proveedores_externos(historial_estado_id);
ALTER TABLE public.proveedores_externos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.proveedores_externos FROM PUBLIC,anon,authenticated;
DO $$
DECLARE col record;
BEGIN
    FOR col IN SELECT attname FROM pg_attribute WHERE attrelid='public.proveedores_externos'::regclass
        AND attnum>0 AND NOT attisdropped LOOP
        EXECUTE format('REVOKE ALL (%I) ON TABLE public.proveedores_externos FROM PUBLIC,anon,authenticated',col.attname);
    END LOOP;
END $$;

CREATE FUNCTION public.proteger_registro_proveedor_externo() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.eleccion_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.reclamos r
            JOIN public.reclamo_elecciones_proveedor ep ON ep.reclamo_id=r.id
            JOIN public.reclamo_historial_estados h ON h.reclamo_id=r.id
            WHERE r.id=NEW.reclamo_id AND r.propiedad_id=NEW.propiedad_id
              AND ep.id=NEW.eleccion_id AND ep.usuario_id=NEW.usuario_id
              AND h.id=NEW.historial_estado_id AND h.usuario_id=NEW.usuario_id
              AND h.estado_nuevo='Derivado a proveedor externo'
        ) THEN
            RAISE EXCEPTION 'El contacto nuevo requiere elección y derivación auditadas';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.eleccion_id IS NOT NULL THEN
        RAISE EXCEPTION 'El registro confirmado de proveedor externo es inmutable';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.proteger_registro_proveedor_externo() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER proteger_registro_proveedor_externo BEFORE INSERT OR UPDATE OR DELETE ON public.proveedores_externos
    FOR EACH ROW EXECUTE FUNCTION public.proteger_registro_proveedor_externo();
COMMIT;
