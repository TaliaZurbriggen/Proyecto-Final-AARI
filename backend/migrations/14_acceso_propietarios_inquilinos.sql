-- AARI-68 / HU6: cuentas vinculadas y seguimiento del correo de bienvenida.
-- Requiere 01_modulo_administracion.sql y 13_autenticacion_usuarios.sql.

create unique index if not exists uq_propietarios_usuario
    on propietarios (usuario_id)
    where usuario_id is not null;

create unique index if not exists uq_inquilinos_usuario
    on inquilinos (usuario_id)
    where usuario_id is not null;

do $$
begin
    if exists (
        select 1
        from propietarios p
        join usuarios u on u.id = p.usuario_id
        where lower(btrim(p.email)) <> lower(btrim(u.email))
           or u.rol <> 'propietario'
    ) or exists (
        select 1
        from inquilinos i
        join usuarios u on u.id = i.usuario_id
        where lower(btrim(i.email)) <> lower(btrim(u.email))
           or u.rol <> 'inquilino'
    ) then
        raise exception using
            message = 'No se puede completar el acceso: hay vínculos existentes con email o rol inconsistente.',
            hint = 'Revisá usuario_id, email y rol de propietarios e inquilinos antes de reintentar.';
    end if;

    if exists (
        with vinculos as (
            select usuario_id from propietarios where usuario_id is not null
            union all
            select usuario_id from inquilinos where usuario_id is not null
        )
        select 1
        from vinculos
        group by usuario_id
        having count(*) > 1
    ) then
        raise exception using
            message = 'No se puede completar el acceso: un usuario está vinculado a más de una persona.',
            hint = 'Cada propietario o inquilino debe tener una cuenta individual.';
    end if;

    if exists (
        with accesos_pendientes as (
            select lower(btrim(email)) as email
            from propietarios
            where usuario_id is null
            union all
            select lower(btrim(email)) as email
            from inquilinos
            where usuario_id is null
        ),
        emails_de_acceso as (
            select lower(btrim(email)) as email from usuarios
            union all
            select email from accesos_pendientes
        )
        select 1
        from emails_de_acceso
        group by email
        having count(*) > 1
    ) then
        raise exception using
            message = 'No se puede crear el acceso: hay emails repetidos entre usuarios, propietarios o inquilinos.',
            hint = 'Corregí los emails duplicados y volvé a ejecutar la migración 14.';
    end if;
end;
$$;

do $$
declare
    persona record;
    nuevo_usuario_id uuid;
begin
    for persona in
        select id, lower(btrim(email)) as email, dni
        from propietarios
        where usuario_id is null
    loop
        insert into usuarios (email, password_hash, rol, primer_ingreso, activo)
        values (
            persona.email,
            crypt(persona.dni, gen_salt('bf')),
            'propietario',
            true,
            true
        )
        returning id into nuevo_usuario_id;

        update propietarios
        set usuario_id = nuevo_usuario_id,
            email = persona.email
        where id = persona.id;
    end loop;

    for persona in
        select id, lower(btrim(email)) as email, dni
        from inquilinos
        where usuario_id is null
    loop
        insert into usuarios (email, password_hash, rol, primer_ingreso, activo)
        values (
            persona.email,
            crypt(persona.dni, gen_salt('bf')),
            'inquilino',
            true,
            true
        )
        returning id into nuevo_usuario_id;

        update inquilinos
        set usuario_id = nuevo_usuario_id,
            email = persona.email
        where id = persona.id;
    end loop;
end;
$$;

create table if not exists entregas_credenciales (
    id                  uuid primary key default gen_random_uuid(),
    usuario_id          uuid not null unique
                        references usuarios(id) on delete cascade,
    destinatario_email  text not null,
    estado              text not null default 'pendiente',
    intentos            integer not null default 0,
    ultimo_error        text,
    enviado_en          timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),

    constraint chk_entregas_credenciales_estado
        check (estado in ('pendiente', 'enviado', 'fallido')),
    constraint chk_entregas_credenciales_intentos
        check (intentos >= 0),
    constraint chk_entregas_credenciales_email
        check (
            destinatario_email
            ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    )
);

-- La aplicación accede a esta información únicamente desde el backend.
-- Evitamos exponer emails y estados de entrega mediante la Data API.
alter table entregas_credenciales enable row level security;
revoke all on table entregas_credenciales from anon, authenticated;

drop trigger if exists trg_entregas_credenciales_updated_at
    on entregas_credenciales;
create trigger trg_entregas_credenciales_updated_at
before update on entregas_credenciales
for each row execute function set_updated_at();

insert into entregas_credenciales (usuario_id, destinatario_email, estado)
select usuario_id, lower(btrim(email)), 'pendiente'
from propietarios
where usuario_id is not null
on conflict (usuario_id) do nothing;

insert into entregas_credenciales (usuario_id, destinatario_email, estado)
select usuario_id, lower(btrim(email)), 'pendiente'
from inquilinos
where usuario_id is not null
on conflict (usuario_id) do nothing;
