-- HU7 / AARI-79. Ejecutar después de 16, previa revisión de datos.
-- No crea operadores ni envía correos. El backend usa conexión privada.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.usuarios ADD COLUMN IF NOT EXISTS nombre_completo text;

-- No inventar nombres para operadores anteriores: completar manualmente antes
-- de ejecutar esta migración si ya existen. Ver README de migraciones.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.usuarios WHERE rol = 'operador'
               AND (nombre_completo IS NULL OR length(trim(nombre_completo)) < 2)) THEN
        RAISE EXCEPTION 'Existen operadores sin nombre. Completar sus nombres antes de migrar.';
    END IF;
END $$;

ALTER TABLE public.usuarios DROP CONSTRAINT IF EXISTS chk_operadores_nombre;
ALTER TABLE public.usuarios ADD CONSTRAINT chk_operadores_nombre CHECK (
    rol <> 'operador' OR (
        nombre_completo IS NOT NULL
        AND char_length(nombre_completo) BETWEEN 2 AND 120
        AND nombre_completo = btrim(nombre_completo)
        AND nombre_completo ~ '^[[:alpha:]]+([ ''’\-][[:alpha:]]+)*$'
    )
);

ALTER TABLE public.reclamos ADD COLUMN IF NOT EXISTS operador_asignado_id uuid
    REFERENCES public.usuarios(id);
CREATE INDEX IF NOT EXISTS idx_reclamos_operador_asignado
    ON public.reclamos(operador_asignado_id);

-- La asignación futura solo puede apuntar a un operador activo. El bloqueo
-- comparte la misma fila que bloquea la baja para impedir asignaciones tardías.
CREATE OR REPLACE FUNCTION public.validar_operador_asignado()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    IF NEW.operador_asignado_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.operador_asignado_id IS DISTINCT FROM OLD.operador_asignado_id) THEN
        PERFORM 1 FROM public.usuarios
        WHERE id = NEW.operador_asignado_id AND rol = 'operador' AND activo
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'La asignación requiere un operador activo.' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.validar_operador_asignado() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS trg_validar_operador_asignado ON public.reclamos;
CREATE TRIGGER trg_validar_operador_asignado
    BEFORE INSERT OR UPDATE OF operador_asignado_id ON public.reclamos
    FOR EACH ROW EXECUTE FUNCTION public.validar_operador_asignado();

ALTER TABLE public.usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reclamos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.usuarios, public.reclamos FROM anon, authenticated;
COMMIT;
