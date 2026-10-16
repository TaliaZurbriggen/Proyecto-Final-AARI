-- HU16 / AARI-180. Archivo generado con Supabase CLI 2.81.3.
-- Preparado y probado localmente; NO aplicar a Supabase compartido sin aprobación.
begin;
set local lock_timeout='5s';
set local statement_timeout='30s';

create table public.reclamo_autorizaciones (
    request_id uuid primary key,
    reclamo_id uuid not null references public.reclamos(id) on delete restrict,
    solicitado_en timestamptz not null,
    expected_updated_at timestamptz not null,
    usuario_id uuid not null references public.usuarios(id) on delete restrict,
    propietario_nombre text not null,
    decision text not null check (decision in ('autorizar','rechazar')),
    estado text not null,
    historial_estado_id uuid not null references public.reclamo_historial_estados(id) on delete restrict,
    decidido_en timestamptz not null,
    constraint uq_autorizacion_solicitud unique (reclamo_id, solicitado_en),
    constraint chk_autorizacion_resultado check (
        (decision='autorizar' and estado='Autorizado') or
        (decision='rechazar' and estado='Rechazado por propietario')
    )
);
create index idx_autorizaciones_usuario on public.reclamo_autorizaciones(usuario_id);
create index idx_autorizaciones_historial on public.reclamo_autorizaciones(historial_estado_id);
alter table public.reclamo_autorizaciones enable row level security;
revoke all on public.reclamo_autorizaciones from public, anon, authenticated;

-- El rechazo cierra este ciclo: ya no impide registrar otro reclamo en la unidad.
-- Se conserva la unicidad para todos los estados activos anteriores.
drop index public.uq_reclamos_inquilino_propiedad_activo;
create unique index uq_reclamos_inquilino_propiedad_activo
    on public.reclamos(inquilino_id, propiedad_id)
    where estado not in ('Resuelto','Resuelto (sin confirmación)','Rechazado por propietario');
commit;
