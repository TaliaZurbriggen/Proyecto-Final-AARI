# Migraciones de base de datos

Scripts SQL para crear y actualizar el esquema de Supabase.

## Instalación nueva

Ejecutar desde el SQL Editor, en este orden:

1. `01_modulo_administracion.sql`
2. `02_modulo_reclamos.sql`
3. `03_modulo_coordinacion.sql`
4. `04_configuracion_sistema.sql`
5. `05_seed_admin.sql` — reemplazar los valores de ejemplo antes de ejecutarlo.
6. `06_clasificacion_agente.sql`

La instalación nueva debe aplicar además, en orden:

1. `13_autenticacion_usuarios.sql` — restricciones e índices de acceso seguro.
2. `14_acceso_propietarios_inquilinos.sql` — cuentas vinculadas, backfill y
   seguimiento del correo de bienvenida.

El módulo de administración inicial ya incorpora el resultado de las
migraciones incrementales 07, 08, 09, 10, 11, 12, 15 y 16. No deben repetirse
en una instalación nueva.

## Instalación existente

Aplicar únicamente las migraciones pendientes y respetar este orden:

1. `07_propietarios_email_unico.sql` — normaliza y hace único el email.
2. `08_propiedades_integridad.sql` — normaliza la dirección y evita duplicados.
3. `09_ubicacion_propiedades.sql` — agrega provincia y localidad, reemplaza
   zona por barrio opcional y convierte el piso a entero (`0` representa PB).
4. `10_ubicacion_propiedades_con_letras.sql` — impide direcciones, localidades
   y barrios formados únicamente por números o símbolos.
5. `11_inquilinos_integridad.sql` — normaliza los datos de inquilinos, hace
   único el email y mantiene consistente el estado con la propiedad asignada.
6. `12_nombres_personas_validos.sql` — normaliza espacios y restringe los
   nombres de propietarios e inquilinos a letras, espacios, apóstrofes y
   guiones. Se detiene si existen registros incompatibles para evitar
   corregir nombres reales de forma automática.
7. `13_autenticacion_usuarios.sql` — normaliza el email de acceso y agrega
   restricciones e índices para intentos fallidos y bloqueos temporales.
8. `14_acceso_propietarios_inquilinos.sql` — crea cuentas para propietarios e
   inquilinos existentes, vincula cada persona con un único usuario y agrega el
   estado persistente del envío de credenciales. La migración se detiene si
   detecta emails repetidos entre identidades de acceso para evitar asignaciones
   ambiguas.
9. `15_proveedores_cobertura_horario.sql` — agrega el horario habitual y las
   tablas de cobertura estructurada. Conserva temporalmente `zona_cobertura`
   para revisar proveedores existentes sin perder información.
10. Completar las coberturas estructuradas de los proveedores que devuelve la
   consulta indicada abajo.
11. `16_finalizar_cobertura_proveedores.sql` — verifica que todos los
    proveedores tengan cobertura válida y recién entonces elimina
    `zona_cobertura`.

La migración 09 se detiene si encuentra propiedades existentes porque provincia
y localidad no pueden inferirse de manera segura. Esos registros deben
completarse antes de volver a ejecutarla.

Las migraciones 01 y 15 habilitan RLS en las cinco tablas de proveedores y
revocan sus permisos a los roles `anon` y `authenticated`. El módulo se consume
exclusivamente a través de FastAPI; por eso no deben agregarse políticas públicas
del Data API sin una nueva decisión de arquitectura y su correspondiente revisión
de seguridad.

La zona anterior no se convierte automáticamente porque un texto libre no
permite inferir con seguridad provincia, localidad, alcance completo y barrios.
Después de aplicar la migración 15, esta consulta identifica los registros que
deben completarse:

```sql
select
    p.id,
    p.nombre_razon_social,
    p.zona_cobertura
from proveedores p
where not exists (
    select 1
    from proveedor_coberturas pc
    where pc.proveedor_id = p.id
)
order by p.nombre_razon_social;
```

Por cada resultado se debe insertar al menos una fila en
`proveedor_coberturas`. Si `cubre_toda_localidad` es `false`, también debe
existir al menos un barrio en `proveedor_cobertura_barrios`. La migración 16 se
puede volver a ejecutar de forma segura: se detendrá sin eliminar la columna
anterior mientras falte algún dato y será un no-op si la columna ya no existe.
