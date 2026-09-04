-- ============================================================
-- HU8 — Alta de reclamos por inquilinos
-- Requiere: migraciones 01 a 18 aplicadas
-- No ejecutar sin validar primero el proyecto y el entorno destino.
-- ============================================================

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

-- El rubro se determina en la clasificación posterior; no se inventa un valor
-- durante el alta inicial.
alter table public.reclamos
    alter column tipo_id drop not null;

-- Número humano visible, independiente del UUID técnico.
create sequence if not exists public.reclamos_numero_seq
    as bigint
    start with 1
    increment by 1
    minvalue 1;

alter table public.reclamos
    add column if not exists numero bigint;

alter sequence public.reclamos_numero_seq
    owned by public.reclamos.numero;

alter table public.reclamos
    alter column numero set default nextval('public.reclamos_numero_seq');

update public.reclamos
set numero = nextval('public.reclamos_numero_seq')
where numero is null;

select setval(
    'public.reclamos_numero_seq',
    greatest(coalesce((select max(numero) from public.reclamos), 0) + 1, 1),
    false
);

alter table public.reclamos
    alter column numero set not null;

create unique index if not exists uq_reclamos_numero
    on public.reclamos (numero);

revoke all on sequence public.reclamos_numero_seq from anon, authenticated;

-- El negocio permite un nuevo alta únicamente cuando todos los anteriores de
-- esa persona y unidad están cerrados.
do $$
begin
    if exists (
        select 1
        from public.reclamos
        where estado not in ('Resuelto', 'Resuelto (sin confirmación)')
        group by inquilino_id, propiedad_id
        having count(*) > 1
    ) then
        raise exception using
            errcode = '23514',
            message = 'Existen reclamos activos duplicados por inquilino y propiedad.';
    end if;
end;
$$;

create unique index if not exists uq_reclamos_inquilino_propiedad_activo
    on public.reclamos (inquilino_id, propiedad_id)
    where estado not in ('Resuelto', 'Resuelto (sin confirmación)');

alter table public.notificaciones
    add column if not exists ultimo_error text,
    add column if not exists updated_at timestamptz not null default now();

-- Las fotos y sus metadatos se consumen exclusivamente a través de FastAPI.
alter table public.reclamo_fotos enable row level security;
alter table public.reclamo_historial_estados enable row level security;
alter table public.notificaciones enable row level security;
revoke all on table public.reclamo_fotos from anon, authenticated;
revoke all on table public.reclamo_historial_estados from anon, authenticated;
revoke all on table public.notificaciones from anon, authenticated;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'reclamos-fotos',
    'reclamos-fotos',
    false,
    5242880,
    array['image/jpeg', 'image/png']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- Serializa altas de fotos para que el límite de tres también sea seguro ante
-- concurrencia. La función no depende del search_path del llamador.
create or replace function public.chk_max_fotos_por_reclamo()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(new.reclamo_id::text, 0)
    );
    if (
        select count(*)
        from public.reclamo_fotos
        where reclamo_id = new.reclamo_id
    ) >= 3 then
        raise exception using
            errcode = '23514',
            message = 'Un reclamo no puede tener más de 3 fotos adjuntas';
    end if;
    return new;
end;
$$;

revoke all on function public.chk_max_fotos_por_reclamo() from public;
revoke all on function public.chk_max_fotos_por_reclamo() from anon, authenticated;

commit;
