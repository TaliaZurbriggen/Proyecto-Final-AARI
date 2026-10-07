-- HU14 / AARI-157. Versión generada por Supabase CLI 2.120.0.
-- Requiere 23_notificaciones_actor_responsable.sql. No cambia datos históricos.
-- HU30 reserva 24/25 y HU13 26: no renombrar sus migraciones aplicadas.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.notificaciones drop constraint if exists chk_notificaciones_tipo_evento;
alter table public.notificaciones add constraint chk_notificaciones_tipo_evento
check (tipo_evento in ('alta_reclamo','estado_reclamo','responsable_inicial',
                      'responsable_recordatorio','responsable_vencido','alerta_operador','expensa_reporte'));

-- Permite que la FK verifique también que la notificación sea del mismo reclamo.
alter table public.notificaciones add constraint uq_notificaciones_id_reclamo unique (id,reclamo_id);
create table public.reclamo_derivaciones_expensa (
    reclamo_id uuid primary key references public.reclamos(id) on delete restrict,
    reporte jsonb not null check (jsonb_typeof(reporte)='object'),
    notificacion_id uuid unique,
    error_configuracion text,
    created_at timestamptz not null default now(),
    constraint fk_derivacion_notificacion foreign key (notificacion_id,reclamo_id)
        references public.notificaciones(id,reclamo_id) on delete restrict,
    constraint chk_derivacion_contacto check (
        (notificacion_id is null and error_configuracion is not null)
        or (notificacion_id is not null and error_configuracion is null)
    )
);

alter table public.notas_internas add constraint chk_notas_internas_contenido
check (char_length(btrim(contenido)) between 1 and 1000) not valid;
-- NOT VALID conserva notas históricas; aplica a todas las nuevas escrituras.
create index idx_expensas_fecha_propiedad on public.reclamos (creado_en desc, numero desc, propiedad_id)
where tipo_gasto='expensa';
create index idx_notas_internas_fecha on public.notas_internas (reclamo_id, created_at desc, id desc);

alter table public.reclamo_derivaciones_expensa enable row level security;
alter table public.notas_internas enable row level security;
alter table public.configuracion_sistema enable row level security;
revoke all on table public.reclamo_derivaciones_expensa, public.notas_internas,
                    public.configuracion_sistema from public, anon, authenticated;
-- Acceso por FastAPI con rol de backend. No hay políticas ni vistas públicas.
commit;
