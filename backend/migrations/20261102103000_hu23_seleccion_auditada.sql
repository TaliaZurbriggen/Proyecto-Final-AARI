-- HU23: vínculo verificable con la decisión real de HU20. No crea decisiones.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE public.reclamo_selecciones_presupuesto
    ADD CONSTRAINT uq_hu23_seleccion_reclamo_presupuesto_proveedor
    UNIQUE(id,reclamo_id,presupuesto_id,proveedor_id);
ALTER TABLE public.aari_visita_coordinaciones ADD COLUMN seleccion_id uuid;
ALTER TABLE public.aari_visita_coordinaciones
    ADD CONSTRAINT fk_visita_seleccion_auditada
    FOREIGN KEY(seleccion_id,reclamo_id,presupuesto_id,proveedor_id)
    REFERENCES public.reclamo_selecciones_presupuesto(id,reclamo_id,presupuesto_id,proveedor_id);
-- Filas anteriores sin vínculo conservan su historia; no se les atribuye una
-- selección retrospectiva. El servicio sólo permite actuar sobre un vínculo real.
DROP INDEX public.uq_visita_coordinacion_seleccion;
CREATE UNIQUE INDEX uq_visita_coordinacion_seleccion
    ON public.aari_visita_coordinaciones(reclamo_id,seleccion_id,seleccion_version)
    WHERE seleccion_id IS NOT NULL;
CREATE INDEX idx_visita_coordinacion_seleccion_auditada
    ON public.aari_visita_coordinaciones(seleccion_id);
COMMIT;
