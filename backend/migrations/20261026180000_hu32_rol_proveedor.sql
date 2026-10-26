-- HU32: ejecutar y confirmar ANTES de la migración de acceso.
-- PostgreSQL no permite usar un valor enum nuevo en su misma transacción.
ALTER TYPE public.rol_usuario ADD VALUE IF NOT EXISTS 'proveedor';
