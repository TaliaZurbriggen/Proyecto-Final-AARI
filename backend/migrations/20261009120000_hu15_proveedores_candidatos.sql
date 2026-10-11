-- HU15 / AARI-170. Aditiva, posterior al main integrado del Sprint 3.
-- No ejecutar en Supabase sin autorización. No se cambian reclamos existentes.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

create table public.reclamo_busquedas_proveedores (
    id uuid primary key default gen_random_uuid(),
    reclamo_id uuid not null references public.reclamos(id) on delete cascade,
    request_id uuid not null,
    request_hash text not null check (length(request_hash) = 64),
    origen text not null check (origen in ('administrador', 'operador', 'agente')),
    usuario_id uuid references public.usuarios(id),
    especialidad_id uuid references public.especialidades(id),
    especialidad_anterior_id uuid references public.especialidades(id),
    provincia text,
    localidad text,
    barrio text,
    resultado text not null check (resultado in (
        'candidatos_encontrados', 'sin_candidatos', 'especialidad_pendiente', 'ubicacion_incompleta'
    )),
    candidato_ids jsonb not null check (jsonb_typeof(candidato_ids) = 'array'),
    aviso_operador text not null check (aviso_operador in ('no_aplica', 'encolado', 'sin_destinatario')),
    buscado_en timestamptz not null default now(),
    unique (reclamo_id, request_id),
    check ((origen = 'agente') = (usuario_id is null)),
    check ((resultado = 'candidatos_encontrados') = (jsonb_array_length(candidato_ids) > 0))
);
create index idx_busquedas_proveedores_reclamo
    on public.reclamo_busquedas_proveedores (reclamo_id, buscado_en desc, id desc);
create index idx_busquedas_proveedores_usuario
    on public.reclamo_busquedas_proveedores (usuario_id);
create index idx_busquedas_proveedores_especialidad
    on public.reclamo_busquedas_proveedores (especialidad_id);
create index idx_busquedas_proveedores_especialidad_anterior
    on public.reclamo_busquedas_proveedores (especialidad_anterior_id);
create index idx_reclamos_pendientes_asignacion
    on public.reclamos (creado_en, id) where estado = 'Pendiente de asignación';
alter table public.reclamo_busquedas_proveedores enable row level security;
revoke all on table public.reclamo_busquedas_proveedores from public, anon, authenticated;
commit;
