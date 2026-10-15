-- HU21 / AARI-229. Generada por Supabase CLI 2.120.0.
-- Tablas oficiales PostgresSaver 3.1.2, versiones de esquema 0..9.
-- No modifica migraciones aplicadas, reclamos ni notificaciones existentes.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

do $$
begin
    if exists (select 1 from public.sesiones_agente
               where estado_grafo <> '{}'::jsonb) then
        raise exception 'Hay sesiones con contexto previo. Revisarlas antes de aplicar HU21; no se sobrescriben.';
    end if;
end;
$$;

alter table public.sesiones_agente
    add column intento_id uuid not null default gen_random_uuid(),
    add column version bigint not null default 0 check (version >= 0),
    add column estado_sesion text not null default 'activa'
        check (estado_sesion in ('activa','expirada','finalizada')),
    add column thread_id text generated always as (reclamo_id::text) stored unique;
alter table public.sesiones_agente enable row level security;
revoke all on public.sesiones_agente from public, anon, authenticated;

create schema aari_coordinacion;
revoke all on schema aari_coordinacion from public, anon, authenticated;

create table aari_coordinacion.checkpoint_migrations (v integer primary key);
create table aari_coordinacion.checkpoints (
    thread_id text not null references public.sesiones_agente(thread_id) on delete cascade,
    checkpoint_ns text not null default '', checkpoint_id text not null,
    parent_checkpoint_id text, type text, checkpoint jsonb not null,
    metadata jsonb not null default '{}',
    primary key (thread_id, checkpoint_ns, checkpoint_id)
);
create table aari_coordinacion.checkpoint_blobs (
    thread_id text not null references public.sesiones_agente(thread_id) on delete cascade,
    checkpoint_ns text not null default '', channel text not null,
    version text not null, type text not null, blob bytea,
    primary key (thread_id, checkpoint_ns, channel, version)
);
create table aari_coordinacion.checkpoint_writes (
    thread_id text not null references public.sesiones_agente(thread_id) on delete cascade,
    checkpoint_ns text not null default '', checkpoint_id text not null,
    task_id text not null, task_path text not null default '', idx integer not null,
    channel text not null, type text, blob bytea not null,
    primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
-- Mismos índices de la librería, sin CONCURRENTLY: tablas nuevas y DDL atómico.
create index checkpoints_thread_id_idx on aari_coordinacion.checkpoints(thread_id);
create index checkpoint_blobs_thread_id_idx on aari_coordinacion.checkpoint_blobs(thread_id);
create index checkpoint_writes_thread_id_idx on aari_coordinacion.checkpoint_writes(thread_id);
insert into aari_coordinacion.checkpoint_migrations(v)
    select generate_series(0,9);

create table aari_coordinacion.eventos (
    reclamo_id uuid not null references public.reclamos(id) on delete cascade,
    evento_id uuid not null,
    usuario_id uuid references public.usuarios(id) on delete set null,
    fingerprint text not null check (length(fingerprint)=64),
    version bigint not null check (version > 0),
    intento_id uuid not null,
    creado_en timestamptz not null default now(),
    primary key (reclamo_id, evento_id)
);
create index eventos_usuario_idx on aari_coordinacion.eventos(usuario_id)
    where usuario_id is not null;
create index sesiones_coordinacion_activas_idx
    on public.sesiones_agente(ultima_actividad, reclamo_id)
    where estado_sesion='activa';

alter table aari_coordinacion.checkpoint_migrations enable row level security;
alter table aari_coordinacion.checkpoints enable row level security;
alter table aari_coordinacion.checkpoint_blobs enable row level security;
alter table aari_coordinacion.checkpoint_writes enable row level security;
alter table aari_coordinacion.eventos enable row level security;
revoke all on all tables in schema aari_coordinacion from public, anon, authenticated;
alter default privileges in schema aari_coordinacion
    revoke all on tables from public, anon, authenticated;
commit;
