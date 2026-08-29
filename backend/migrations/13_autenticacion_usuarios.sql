-- AARI-56: endurecimiento incremental de la tabla usuarios para autenticación.
-- Requiere 01_modulo_administracion.sql.

update usuarios
set email = lower(btrim(email));

create unique index if not exists uq_usuarios_email_normalizado
    on usuarios (lower(email));

alter table usuarios
    add constraint chk_usuarios_intentos_fallidos
    check (intentos_fallidos between 0 and 3);

create index if not exists idx_usuarios_bloqueado_hasta
    on usuarios (bloqueado_hasta)
    where bloqueado_hasta is not null;
