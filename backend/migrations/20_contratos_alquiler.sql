-- HU29 / AARI-318. Ejecutar después de 19_alta_reclamos.sql.
-- Conserva los participantes, PDFs e historial; no agrega fecha de firma.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
create schema if not exists extensions;
create extension if not exists btree_gist with schema extensions;
set local search_path = public, extensions;

create table public.contratos (
    id uuid primary key,
    inquilino_id uuid not null references public.inquilinos(id) on delete restrict,
    propietario_id uuid not null references public.propietarios(id) on delete restrict,
    propiedad_id uuid not null references public.propiedades(id) on delete restrict,
    contrato_anterior_id uuid references public.contratos(id) on delete restrict,
    fecha_inicio date not null,
    fecha_fin date not null,
    fecha_finalizacion date,
    estado text not null default 'borrador',
    revision integer not null default 1,
    creado_por uuid references public.usuarios(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_contratos_fechas check (fecha_fin > fecha_inicio),
    constraint chk_contratos_estado check (estado in ('borrador', 'firmado', 'finalizado')),
    constraint chk_contratos_revision check (revision >= 1),
    constraint chk_contratos_finalizacion check (
        (estado = 'finalizado' and fecha_finalizacion is not null
            and fecha_finalizacion between fecha_inicio and fecha_fin)
        or (estado <> 'finalizado' and fecha_finalizacion is null)
    ),
    constraint chk_contratos_anterior check (contrato_anterior_id is distinct from id),
    -- Incluye futuros firmados y períodos históricos, no solo el día de hoy.
    constraint ex_contratos_periodo exclude using gist (
        propiedad_id with =,
        daterange(fecha_inicio, coalesce(fecha_finalizacion, fecha_fin), '[]') with &&
    ) where (estado in ('firmado', 'finalizado'))
);
create index idx_contratos_inquilino on public.contratos(inquilino_id);
create index idx_contratos_propietario on public.contratos(propietario_id);
create index idx_contratos_anterior on public.contratos(contrato_anterior_id);

create table public.contrato_documentos (
    id uuid primary key,
    contrato_id uuid not null references public.contratos(id) on delete restrict,
    version integer not null check (version >= 1),
    storage_path text not null unique,
    nombre_archivo text not null check (char_length(nombre_archivo) between 1 and 180),
    tamano integer not null check (tamano between 1 and 10485760),
    sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
    firmado boolean not null default false,
    creado_por uuid references public.usuarios(id) on delete set null,
    created_at timestamptz not null default now(),
    unique (contrato_id, version)
);

create table public.contrato_eventos (
    id uuid primary key,
    contrato_id uuid not null references public.contratos(id) on delete restrict,
    accion text not null check (accion in ('creado', 'editado', 'documento', 'confirmado', 'finalizado')),
    revision integer not null,
    actor_id uuid references public.usuarios(id) on delete set null,
    created_at timestamptz not null default now()
);
create index idx_contrato_eventos_contrato on public.contrato_eventos(contrato_id);

alter table public.contratos enable row level security;
alter table public.contrato_documentos enable row level security;
alter table public.contrato_eventos enable row level security;
revoke all on public.contratos, public.contrato_documentos, public.contrato_eventos
    from public, anon, authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('contratos-alquiler', 'contratos-alquiler', false, 10485760, array['application/pdf'])
on conflict (id) do update set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
commit;
