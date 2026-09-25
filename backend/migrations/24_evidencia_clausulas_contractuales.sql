begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.contrato_analisis
    add column propuestas_rechazadas jsonb not null default '[]'::jsonb;

alter table public.contrato_clausulas
    add column evidencias jsonb not null default '[]'::jsonb,
    add column uso_clasificador text not null default 'operativa',
    add constraint ck_contrato_clausulas_uso_clasificador
        check (uso_clasificador in ('operativa', 'contexto', 'excluir'));

commit;
