begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.contrato_analisis
    add column modo text not null default 'ia' check (modo in ('ia', 'literal')),
    add column ejecucion_id uuid,
    add column propuestas_fuente_rechazadas jsonb not null default '[]'::jsonb;
alter table public.contrato_clausulas
    add column origen text not null default 'ia' check (origen in ('ia', 'literal'));

create table public.contrato_analisis_intentos (
    id uuid primary key,
    analisis_id uuid not null references public.contrato_analisis(id) on delete restrict,
    modo text not null check (modo in ('ia', 'literal')),
    modelo text not null,
    prompt_version text not null,
    extractor_version text not null,
    estado text not null check (estado in ('procesando', 'completado', 'incompleto', 'fallido', 'interrumpido')),
    resultado jsonb not null default '{}'::jsonb,
    error text,
    iniciado_en timestamptz not null default now(),
    finalizado_en timestamptz
);
create index idx_contrato_analisis_intentos_analisis
    on public.contrato_analisis_intentos(analisis_id, iniciado_en, id);
alter table public.contrato_analisis_intentos enable row level security;
revoke all on public.contrato_analisis_intentos from public, anon, authenticated;
-- Las filas y propuestas anteriores permanecen intactas. Los intentos nuevos
-- mantienen su evidencia incluso cuando una respuesta llega después de su lease.
commit;
