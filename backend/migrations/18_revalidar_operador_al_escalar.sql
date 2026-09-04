-- HU7 / AARI-79, corrección del PR #21. Ejecutar después de 17.
-- No reemplazar 17: ya fue aplicada en la base compartida.
-- No modifica asignaciones existentes ni envía correos.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE OR REPLACE FUNCTION public.validar_operador_asignado()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    IF NEW.operador_asignado_id IS NOT NULL
       AND (
           TG_OP = 'INSERT'
           OR NEW.operador_asignado_id IS DISTINCT FROM OLD.operador_asignado_id
           OR (NEW.estado = 'Escalado' AND NEW.estado IS DISTINCT FROM OLD.estado)
       ) THEN
        -- Misma fila y bloqueo que en 17: serializa con la baja del operador.
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
    BEFORE INSERT OR UPDATE OF operador_asignado_id, estado ON public.reclamos
    FOR EACH ROW EXECUTE FUNCTION public.validar_operador_asignado();

-- El DDL anterior mantiene bloqueada la tabla hasta COMMIT. No corregir datos
-- reales automáticamente: si el fallo ya ocurrió, revisar esas asignaciones.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.reclamos AS r
        WHERE r.estado = 'Escalado' AND r.operador_asignado_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM public.usuarios AS u
              WHERE u.id = r.operador_asignado_id AND u.rol = 'operador' AND u.activo
          )
    ) THEN
        RAISE EXCEPTION 'Existen reclamos escalados con operador inválido. Revisar sus asignaciones antes de migrar.'
            USING ERRCODE = '23514';
    END IF;
END $$;
COMMIT;
