-- HU19: recepción, procedencia de presupuestos y cierre de rondas. Sólo QA local.
-- Requiere las dos migraciones HU19 anteriores. No aplicada en Supabase.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';

alter table public.reclamo_rondas_presupuesto
    add column recepcion_estado text not null default 'sin_envios'
        check (recepcion_estado in ('sin_envios','esperando','disponibles','sin_presupuestos','revision','cancelada')),
    add column iniciada_en timestamptz,
    add column respuesta_vence_en timestamptz,
    add column cerrada_en timestamptz,
    add constraint chk_ronda_recepcion_fechas check (
        (iniciada_en is null and respuesta_vence_en is null)
        or (iniciada_en is not null and respuesta_vence_en > iniciada_en));
create index idx_rondas_presupuesto_vencimiento on public.reclamo_rondas_presupuesto(respuesta_vence_en,id)
    where cerrada_en is null;

alter table public.proveedor_solicitudes_presupuesto
    add column respuesta_vence_en timestamptz,
    add column entrega_fallida_en timestamptz,
    add constraint uq_solicitud_contexto_presupuesto unique (id,reclamo_id,proveedor_id);

-- Derivar sólo las fechas nuevas de aceptaciones durables anteriores, sin
-- reiniciar el plazo ni emitir avisos al ejecutar DDL.
update public.proveedor_solicitudes_presupuesto
set respuesta_vence_en=aceptado_en+interval '24 hours'
where estado='aceptada' and aceptado_en is not null;
update public.reclamo_rondas_presupuesto rp
set iniciada_en=times.first_accepted,respuesta_vence_en=times.last_deadline,recepcion_estado='esperando'
from (select ronda_id,min(aceptado_en) as first_accepted,max(respuesta_vence_en) as last_deadline
      from public.proveedor_solicitudes_presupuesto where respuesta_vence_en is not null group by ronda_id) times
where rp.id=times.ronda_id;

-- Los presupuestos históricos no tienen moneda/procedencia comprobada: no inventarlas.
alter table public.presupuestos
    add column moneda text check (moneda in ('ARS','USD')),
    add column solicitud_presupuesto_id uuid unique
        references public.proveedor_solicitudes_presupuesto(id) on delete restrict,
    add column mensaje_entrada_id uuid unique
        references public.whatsapp_eventos_entrada(id) on delete restrict,
    add constraint chk_presupuesto_procedencia check (
        (solicitud_presupuesto_id is null and mensaje_entrada_id is null)
        or (solicitud_presupuesto_id is not null and mensaje_entrada_id is not null and moneda is not null)),
    add constraint fk_presupuesto_solicitud_contexto foreign key (solicitud_presupuesto_id,reclamo_id,proveedor_id)
        references public.proveedor_solicitudes_presupuesto(id,reclamo_id,proveedor_id) on delete restrict;
alter table public.presupuestos enable row level security;
revoke all on public.presupuestos from public,anon,authenticated;

create table public.presupuesto_respuestas (
    id uuid primary key default gen_random_uuid(),
    mensaje_entrada_id uuid not null unique references public.whatsapp_eventos_entrada(id) on delete restrict,
    solicitud_id uuid references public.proveedor_solicitudes_presupuesto(id) on delete restrict,
    presupuesto_id uuid unique references public.presupuestos(id) on delete restrict,
    resultado text not null check (resultado in ('aceptada','revision','ignorada','tardia')),
    motivo text not null,
    procesada_en timestamptz not null default clock_timestamp(),
    check ((resultado='aceptada') = (presupuesto_id is not null))
);
create index idx_presupuesto_respuestas_solicitud on public.presupuesto_respuestas(solicitud_id);
alter table public.presupuesto_respuestas enable row level security;
revoke all on public.presupuesto_respuestas from public,anon,authenticated;
commit;
