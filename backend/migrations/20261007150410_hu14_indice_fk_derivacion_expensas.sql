-- HU14 / AARI-157. Versión generada por Supabase CLI 2.120.0.
-- Requiere 20261007133447_hu14_derivacion_expensas.sql.
-- Incremental: conserva el SQL/historial aplicado, los datos y los permisos.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';

create index idx_derivaciones_expensa_notificacion_reclamo
    on public.reclamo_derivaciones_expensa (notificacion_id, reclamo_id);

commit;
