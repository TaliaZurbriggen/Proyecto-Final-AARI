-- HU19: solicitudes/outbox, sin envíos ni transiciones al aplicar.
-- Requiere HU15, HU16 y HU17. NO aplicada en Supabase; requiere autorización.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';

create table public.reclamo_rondas_presupuesto (
    id uuid primary key default gen_random_uuid(),
    reclamo_id uuid not null references public.reclamos(id) on delete restrict,
    eleccion_id uuid not null unique,
    huella text not null check (huella ~ '^[0-9a-f]{64}$'),
    contexto jsonb not null check (jsonb_typeof(contexto)='object'),
    resultado text not null check (resultado in ('preparada','sin_candidatos','revision')),
    motivo text,
    creado_en timestamptz not null default clock_timestamp(),
    unique(id,reclamo_id),
    foreign key (eleccion_id,reclamo_id) references public.reclamo_elecciones_proveedor(id,reclamo_id) on delete restrict
);
create index idx_rondas_presupuesto_reclamo on public.reclamo_rondas_presupuesto(reclamo_id);

create table public.proveedor_solicitudes_presupuesto (
    id uuid primary key,
    ronda_id uuid not null,
    reclamo_id uuid not null,
    proveedor_id uuid not null references public.proveedores(id) on delete restrict,
    destinatario text not null check (destinatario ~ '^[1-9][0-9]{5,14}$'),
    parametros jsonb not null check (jsonb_typeof(parametros)='array' and jsonb_array_length(parametros)=4),
    mensaje text not null check (length(mensaje) between 1 and 20000),
    version_plantilla text not null,
    estado text not null default 'pendiente' check (estado in
        ('pendiente','reservada','enviando','aceptada','rechazada','desconocida','omitida')),
    motivo text,
    reserva_token uuid,
    reserva_hasta timestamptz,
    intentos integer not null default 0 check (intentos between 0 and 1),
    intento_en timestamptz,
    aceptado_en timestamptz,
    plantilla_meta text,
    idioma text,
    waba_id text,
    telefono_id text,
    mensaje_externo_id text,
    creado_en timestamptz not null default clock_timestamp(),
    actualizado_en timestamptz not null default clock_timestamp(),
    unique(ronda_id,proveedor_id),
    unique(waba_id,telefono_id,mensaje_externo_id),
    foreign key (ronda_id,reclamo_id) references public.reclamo_rondas_presupuesto(id,reclamo_id) on delete restrict,
    check ((estado in ('reservada','enviando')) = (reserva_hasta is not null)),
    check (estado not in ('reservada','enviando','desconocida','aceptada','rechazada') or reserva_token is not null),
    check ((intentos=0 and intento_en is null) or (intentos=1 and intento_en is not null)),
    check (estado not in ('enviando','desconocida','aceptada','rechazada') or intentos=1),
    check (estado<>'aceptada' or (aceptado_en is not null and mensaje_externo_id is not null)),
    check (waba_id is null or waba_id ~ '^[0-9]{1,32}$'),
    check (telefono_id is null or telefono_id ~ '^[0-9]{1,32}$')
);
create index idx_solicitudes_presupuesto_reclamo on public.proveedor_solicitudes_presupuesto(reclamo_id);
create index idx_solicitudes_presupuesto_proveedor on public.proveedor_solicitudes_presupuesto(proveedor_id);
create index idx_solicitudes_presupuesto_ronda_reclamo on public.proveedor_solicitudes_presupuesto(ronda_id,reclamo_id);
create index idx_solicitudes_presupuesto_pendientes on public.proveedor_solicitudes_presupuesto(creado_en,id) where estado='pendiente';
create index idx_solicitudes_presupuesto_reservas on public.proveedor_solicitudes_presupuesto(reserva_hasta,id) where estado in ('reservada','enviando');

create table public.solicitud_presupuesto_eventos (
    id uuid primary key default gen_random_uuid(),
    solicitud_id uuid not null references public.proveedor_solicitudes_presupuesto(id) on delete restrict,
    tipo text not null check (tipo in ('preparada','reservada','reserva_liberada','enviando','aceptada','rechazada','desconocida','omitida')),
    motivo text,
    intento_id uuid,
    creado_en timestamptz not null default clock_timestamp()
);
create index idx_solicitud_presupuesto_eventos_solicitud on public.solicitud_presupuesto_eventos(solicitud_id,creado_en,id);
alter table public.reclamo_rondas_presupuesto enable row level security;
alter table public.proveedor_solicitudes_presupuesto enable row level security;
alter table public.solicitud_presupuesto_eventos enable row level security;
revoke all on public.reclamo_rondas_presupuesto, public.proveedor_solicitudes_presupuesto,
    public.solicitud_presupuesto_eventos from public,anon,authenticated;
commit;
