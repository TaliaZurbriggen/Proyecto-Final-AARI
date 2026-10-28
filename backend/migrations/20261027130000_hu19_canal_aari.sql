-- HU19: canal AARI independiente de eventos/IDs de Meta. Requiere HU16/17/32.
-- No ejecuta workers, crea solicitudes ni envía correo al aplicar.
BEGIN;
CREATE TABLE public.aari_rondas_presupuesto (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reclamo_id uuid NOT NULL REFERENCES public.reclamos(id) ON DELETE RESTRICT,
    eleccion_id uuid NOT NULL UNIQUE,
    huella text NOT NULL CHECK (huella ~ '^[0-9a-f]{64}$'),
    contexto jsonb NOT NULL,
    exclusiones jsonb NOT NULL DEFAULT '[]',
    estado text NOT NULL CHECK (estado IN ('esperando','disponibles','sin_presupuestos','revision','cancelada')),
    publicada_en timestamptz NOT NULL,
    vence_en timestamptz,
    cerrada_en timestamptz,
    UNIQUE(id,reclamo_id),
    FOREIGN KEY(eleccion_id,reclamo_id) REFERENCES public.reclamo_elecciones_proveedor(id,reclamo_id),
    CHECK (vence_en IS NULL OR vence_en > publicada_en),
    CHECK (jsonb_typeof(contexto)='object' AND jsonb_typeof(exclusiones)='array')
);
CREATE TABLE public.aari_solicitudes_presupuesto (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ronda_id uuid NOT NULL,
    reclamo_id uuid NOT NULL,
    proveedor_id uuid NOT NULL REFERENCES public.proveedores(id) ON DELETE RESTRICT,
    usuario_id uuid NOT NULL REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    publicada_en timestamptz NOT NULL,
    vence_en timestamptz NOT NULL CHECK (vence_en > publicada_en),
    aviso_id uuid REFERENCES public.notificaciones(id) ON DELETE RESTRICT,
    respuesta_request_id uuid UNIQUE,
    UNIQUE(ronda_id,proveedor_id),
    UNIQUE(id,reclamo_id,proveedor_id,usuario_id),
    FOREIGN KEY(ronda_id,reclamo_id) REFERENCES public.aari_rondas_presupuesto(id,reclamo_id)
);
ALTER TABLE public.presupuestos ADD COLUMN IF NOT EXISTS moneda text;
ALTER TABLE public.presupuestos
    ADD COLUMN tipo_importe text CHECK (tipo_importe IN ('exacto','minimo')),
    ADD COLUMN solicitud_aari_id uuid UNIQUE,
    ADD COLUMN presentado_por uuid REFERENCES public.usuarios(id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_presupuesto_solicitud_aari FOREIGN KEY(solicitud_aari_id,reclamo_id,proveedor_id,presentado_por)
        REFERENCES public.aari_solicitudes_presupuesto(id,reclamo_id,proveedor_id,usuario_id),
    ADD CONSTRAINT chk_presupuesto_aari CHECK (solicitud_aari_id IS NULL OR
        (moneda IN ('ARS','USD') AND moneda IS NOT NULL AND tipo_importe IS NOT NULL AND presentado_por IS NOT NULL
         AND descripcion IS NOT NULL AND length(btrim(descripcion)) BETWEEN 10 AND 2000));
-- No atribuir tipo exacto/moneda a presupuestos históricos: se conservan NULL.
CREATE TABLE public.aari_presupuesto_eventos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ronda_id uuid NOT NULL REFERENCES public.aari_rondas_presupuesto(id),
    solicitud_id uuid REFERENCES public.aari_solicitudes_presupuesto(id),
    actor_id uuid REFERENCES public.usuarios(id),
    tipo text NOT NULL CHECK (tipo IN ('publicada','presupuesto_registrado','vencida','cancelada','revision')),
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX idx_aari_rondas_reclamo ON public.aari_rondas_presupuesto(reclamo_id);
CREATE INDEX idx_aari_rondas_vencimiento ON public.aari_rondas_presupuesto(vence_en,id) WHERE cerrada_en IS NULL;
CREATE INDEX idx_aari_solicitudes_usuario ON public.aari_solicitudes_presupuesto(usuario_id,publicada_en DESC,id);
CREATE INDEX idx_aari_solicitudes_proveedor ON public.aari_solicitudes_presupuesto(proveedor_id);
CREATE INDEX idx_aari_solicitudes_contexto ON public.aari_solicitudes_presupuesto(ronda_id,reclamo_id);
CREATE INDEX idx_aari_solicitudes_aviso ON public.aari_solicitudes_presupuesto(aviso_id);
CREATE INDEX idx_aari_eventos_ronda ON public.aari_presupuesto_eventos(ronda_id,creado_en,id);
CREATE INDEX idx_aari_eventos_solicitud ON public.aari_presupuesto_eventos(solicitud_id);
CREATE INDEX idx_aari_eventos_actor ON public.aari_presupuesto_eventos(actor_id);
CREATE INDEX idx_presupuestos_presentado_por ON public.presupuestos(presentado_por);
ALTER TABLE public.aari_rondas_presupuesto ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_solicitudes_presupuesto ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aari_presupuesto_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.presupuestos ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.aari_rondas_presupuesto,public.aari_solicitudes_presupuesto,
    public.aari_presupuesto_eventos,public.presupuestos FROM PUBLIC,anon,authenticated;
COMMIT;
