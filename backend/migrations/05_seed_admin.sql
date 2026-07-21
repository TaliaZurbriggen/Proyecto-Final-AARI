-- ============================================================
-- AARI — Seed: usuario administrador inicial
-- Requiere: 01_modulo_administracion.sql ya ejecutado
--           (usa pgcrypto, habilitado en ese script)
-- ============================================================

-- ------------------------------------------------------------
-- IMPORTANTE:
-- Reemplazá los valores de :'admin_email' y :'admin_password'
-- antes de correr este script. No dejar credenciales reales
-- versionadas en el repo.
--
-- Podés setearlas como variables de sesión en el SQL Editor así:
--
--   \set admin_email 'admin@oikos.com'
--   \set admin_password 'CAMBIAR_ESTA_CLAVE_TEMPORAL'
--
-- Si el SQL Editor de Supabase no soporta \set (psql-only),
-- reemplazá directamente el texto en el insert de abajo.
-- ------------------------------------------------------------

insert into usuarios (email, password_hash, rol, primer_ingreso, activo)
values (
    'admin@oikos.com',                                  -- <-- reemplazar por el email real
    crypt('CAMBIAR_ESTA_CLAVE_TEMPORAL', gen_salt('bf')), -- <-- reemplazar por la clave real
    'administrador',
    true,   -- fuerza cambio de contraseña en el primer ingreso, igual que HU6
    true
)
on conflict (email) do nothing;

-- ------------------------------------------------------------
-- Verificación manual del hash (opcional, para probar login):
-- select (password_hash = crypt('CAMBIAR_ESTA_CLAVE_TEMPORAL', password_hash)) as coincide
-- from usuarios where email = 'admin@oikos.com';
-- ------------------------------------------------------------