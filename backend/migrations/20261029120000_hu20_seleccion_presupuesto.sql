-- HU20: auditoría aditiva. Sólo aplicar al entorno compartido con autorización.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE public.presupuestos ADD CONSTRAINT uq_presupuesto_id_reclamo_proveedor
    UNIQUE(id,reclamo_id,proveedor_id);
CREATE TABLE public.reclamo_selecciones_presupuesto (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reclamo_id uuid NOT NULL REFERENCES public.reclamos(id) ON DELETE RESTRICT,
    eleccion_id uuid NOT NULL UNIQUE,
    ronda_id uuid NOT NULL UNIQUE,
    request_id uuid NOT NULL UNIQUE,
    expected_updated_at timestamptz NOT NULL,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    actor_nombre text NOT NULL,
    modalidad text NOT NULL CHECK(modalidad='fidelizado'),
    presupuesto_id uuid NOT NULL,
    proveedor_id uuid NOT NULL REFERENCES public.proveedores(id) ON DELETE RESTRICT,
    proveedor_nombre text NOT NULL,
    monto numeric(12,2) NOT NULL CHECK(monto>0),
    moneda text NOT NULL CHECK(moneda IN ('ARS','USD')),
    tipo_importe text NOT NULL CHECK(tipo_importe IN ('exacto','minimo')),
    estado_resultante text NOT NULL CHECK(estado_resultante='Proveedor seleccionado'),
    decidido_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    historial_estado_id uuid NOT NULL REFERENCES public.reclamo_historial_estados(id) ON DELETE RESTRICT,
    FOREIGN KEY(eleccion_id,reclamo_id) REFERENCES public.reclamo_elecciones_proveedor(id,reclamo_id),
    FOREIGN KEY(ronda_id,reclamo_id) REFERENCES public.aari_rondas_presupuesto(id,reclamo_id),
    FOREIGN KEY(presupuesto_id,reclamo_id,proveedor_id) REFERENCES public.presupuestos(id,reclamo_id,proveedor_id)
);
CREATE INDEX idx_seleccion_presupuesto_reclamo ON public.reclamo_selecciones_presupuesto(reclamo_id);
CREATE INDEX idx_seleccion_presupuesto_usuario ON public.reclamo_selecciones_presupuesto(usuario_id);
CREATE INDEX idx_seleccion_presupuesto_historial ON public.reclamo_selecciones_presupuesto(historial_estado_id);
CREATE INDEX idx_seleccion_presupuesto_proveedor ON public.reclamo_selecciones_presupuesto(proveedor_id);
CREATE INDEX idx_seleccion_presupuesto_presupuesto ON public.reclamo_selecciones_presupuesto(presupuesto_id,reclamo_id,proveedor_id);
ALTER TABLE public.reclamo_selecciones_presupuesto ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reclamo_selecciones_presupuesto FROM PUBLIC,anon,authenticated;
COMMIT;
