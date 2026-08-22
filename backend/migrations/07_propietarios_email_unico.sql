-- AARI-9 — El email identifica de forma unívoca al propietario.
-- Esta migración complementa instalaciones que ya ejecutaron el módulo 1.

update propietarios
set email = lower(trim(email))
where email <> lower(trim(email));

create unique index if not exists uq_propietarios_email_normalizado
    on propietarios (lower(email));
