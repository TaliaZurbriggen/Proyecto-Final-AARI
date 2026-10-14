-- Incremental: no modifica ni repite la migración base ya aplicada.
-- Aplicación en Supabase requiere autorización explícita.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
create table public.reclamo_tareas_proveedores (
    reclamo_id uuid primary key references public.reclamos(id) on delete cascade,
    input_hash text not null check (length(input_hash)=64),
    request_id uuid not null unique default gen_random_uuid(),
    estado text not null default 'pendiente' check (estado in ('pendiente','procesando','completada','revision','cancelada')),
    reserva_token uuid,
    reserva_hasta timestamptz,
    motivo text,
    fuente text check (fuente in ('registrada','modelo','revision')),
    modelo text,
    prompt_version text,
    actualizado_en timestamptz not null default clock_timestamp(),
    check ((estado='procesando') = (reserva_token is not null and reserva_hasta is not null)),
    check ((reserva_token is null) = (reserva_hasta is null))
);
create index idx_tareas_proveedores_pendientes on public.reclamo_tareas_proveedores (actualizado_en,reclamo_id)
    where estado='pendiente';
alter table public.reclamo_tareas_proveedores enable row level security;
revoke all on table public.reclamo_tareas_proveedores from public, anon, authenticated;
commit;
