begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.contrato_documentos
    add constraint uq_contrato_documentos_contrato_documento
    unique (contrato_id, id);

create table public.contrato_analisis (
    id uuid primary key,
    contrato_id uuid not null,
    documento_id uuid not null unique,
    estado text not null default 'pendiente'
        check (estado in ('pendiente', 'procesando', 'completado', 'incompleto', 'fallido')),
    completo boolean not null default false,
    paginas_total integer check (paginas_total is null or paginas_total > 0),
    lectura_paginas jsonb not null default '[]'::jsonb,
    extractor_version text not null,
    prompt_version text not null,
    modelo text not null,
    intentos integer not null default 0 check (intentos between 0 and 3),
    ultimo_error text,
    solicitado_por uuid references public.usuarios(id) on delete set null,
    proximo_intento_en timestamptz not null default now(),
    bloqueado_hasta timestamptz,
    iniciado_en timestamptz,
    finalizado_en timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint fk_contrato_analisis_documento
        foreign key (contrato_id, documento_id)
        references public.contrato_documentos(contrato_id, id)
        on delete restrict
);

create index idx_contrato_analisis_pendientes
    on public.contrato_analisis(proximo_intento_en, created_at)
    where estado in ('pendiente', 'procesando');
create index idx_contrato_analisis_contrato
    on public.contrato_analisis(contrato_id, created_at desc);

create table public.contrato_clausulas (
    id uuid primary key,
    analisis_id uuid not null references public.contrato_analisis(id) on delete restrict,
    ordinal integer not null check (ordinal > 0),
    numero text,
    titulo text,
    paginas jsonb not null default '[]'::jsonb,
    texto_original text not null check (length(trim(texto_original)) > 0),
    resumen text not null check (length(trim(resumen)) > 0),
    categoria text not null check (categoria in (
        'reparacion', 'mantenimiento', 'danio', 'servicio', 'expensa',
        'aviso', 'acceso', 'devolucion', 'otro'
    )),
    responsable text not null check (responsable in (
        'inquilino', 'propietario', 'administracion', 'condicional', 'no_especificado'
    )),
    condiciones text,
    referencias jsonb not null default '[]'::jsonb,
    confianza numeric(4,3) not null check (confianza between 0 and 1),
    estado_revision text not null default 'pendiente'
        check (estado_revision in ('pendiente', 'confirmada', 'editada', 'descartada')),
    propuesta_original jsonb not null,
    revision integer not null default 1 check (revision > 0),
    revisado_por uuid references public.usuarios(id) on delete set null,
    revisado_en timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (analisis_id, ordinal)
);

create index idx_contrato_clausulas_analisis
    on public.contrato_clausulas(analisis_id, ordinal);
create index idx_contrato_clausulas_confirmadas
    on public.contrato_clausulas(analisis_id)
    where estado_revision in ('confirmada', 'editada');

create table public.contrato_clausula_eventos (
    id uuid primary key,
    clausula_id uuid not null references public.contrato_clausulas(id) on delete restrict,
    accion text not null check (accion in ('confirmada', 'editada', 'descartada')),
    revision integer not null check (revision > 0),
    valor_anterior jsonb not null,
    valor_nuevo jsonb not null,
    actor_id uuid references public.usuarios(id) on delete set null,
    created_at timestamptz not null default now()
);

create index idx_contrato_clausula_eventos_clausula
    on public.contrato_clausula_eventos(clausula_id, created_at, id);

alter table public.reclamos
    add column contexto_contractual_clasificacion jsonb not null default '[]'::jsonb;

alter table public.contrato_analisis enable row level security;
alter table public.contrato_clausulas enable row level security;
alter table public.contrato_clausula_eventos enable row level security;

revoke all on public.contrato_analisis, public.contrato_clausulas,
    public.contrato_clausula_eventos from public, anon, authenticated;

commit;
