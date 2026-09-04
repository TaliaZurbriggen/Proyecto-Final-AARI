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
3. `17_usuarios_operadores.sql` — nombres de operadores y asignación de
   reclamos. También es necesaria en instalaciones nuevas.
4. `18_revalidar_operador_al_escalar.sql` — revalida asignaciones al pasar a
   `Escalado`, aunque no cambie el operador.

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
12. `17_usuarios_operadores.sql` — agrega el nombre del operador, una referencia
    opcional desde reclamos, su índice y validación de asignaciones a operadores
    activos. Aplicar después de la revisión indicada abajo.
13. `18_revalidar_operador_al_escalar.sql` — corrige el trigger y su función
    para revalidar también al entrar al estado `Escalado`. No reemplaza la 17.

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

## HU7: preparación y validación de la migración 17

La migración es aditiva y transaccional: no crea cuentas, no modifica
contraseñas y no envía correos. Debe aplicarse con autorización al proyecto y
entorno correctos antes de usar la API de operadores. Mantiene RLS en
`usuarios` y `reclamos` y revoca permisos de `anon` y `authenticated`; el acceso
sigue siendo a través del backend, no del Data API de Supabase.

**Aplicación confirmada:** en el proyecto compartido AARI de desarrollo se
ejecutó el 02/09/2026 y quedó registrada como
`20260902235524_hu7_usuarios_operadores`. No repetirla por cada integrante ni
por cada pull. En otras bases, comprobar primero su historial y estructura.
El archivo limita la espera de bloqueos a 5 segundos y cada sentencia a
30 segundos; si vence el límite, la transacción no se confirma.
La evidencia y las pruebas optativas están en `docs/hu7_validacion_supabase.md`
desde la raíz del repositorio.

Antes de ejecutarla, revisar si existen operadores:

```sql
select count(*) as operadores_existentes
from public.usuarios
where rol = 'operador';
```

Si hay operadores previos sin nombre, la migración se detiene y revierte toda
su transacción, incluida la columna nueva. **No se deben inventar nombres ni
borrar cuentas para continuar.** Con autorización, preparar la columna en una
operación separada:

```sql
alter table public.usuarios
    add column if not exists nombre_completo text;
```

Completar después los nombres reales de esas cuentas mediante un canal
administrativo seguro, identificando cada cuenta por su ID. No pegar datos
personales en scripts versionados. Los nombres deben tener entre 2 y 120
caracteres, solo letras Unicode, espacios simples, apóstrofes o guiones, sin
espacios en los extremos. Una vez completados y revisados, ejecutar el script
17 completo. Si una herramienta deja una transacción fallida abierta, cerrarla
con `ROLLBACK` antes de corregir los datos y volver a ejecutar.

Después de aplicarlo, validar:

- Existencia de `usuarios.nombre_completo`, `reclamos.operador_asignado_id`,
  la FK, `idx_reclamos_operador_asignado` y el trigger de asignación.
- Rechazo de nuevas asignaciones a cuentas inactivas o de otro rol. Las
  asignaciones históricas no modificadas pueden conservar un operador inactivo.
- Alta, unicidad global, hash real, primer ingreso y baja transaccional en un
  entorno autorizado. Probar rollback y concurrencia en PostgreSQL: los dobles
  SQLite de la suite local no validan bloqueos ni `pgcrypto`.
- RLS y ausencia de permisos públicos inesperados. Revisar los asesores de
  seguridad y rendimiento de Supabase después del cambio.

Usar un remitente simulado en pruebas automatizadas. El envío SMTP real
requiere autorización específica y un destinatario de prueba acordado.

## HU7: corrección incremental 18 (PR #21)

**Aplicada con autorización al Supabase compartido AARI de desarrollo el
03/09/2026 (Argentina)**, historial
`20260904001512_hu7_revalidar_operador_al_escalar` (versión UTC).
No repetirla por integrante ni por pull. La 17 permanece intacta,
con su historial y hash. En otras bases, aplicar esta corrección después de 17 tanto en
bases existentes como en instalaciones nuevas. No hay cambios de `.env`,
dependencias, cuentas o correos.

El trigger ahora observa `operador_asignado_id` y `estado`; la función valida
inserciones, cambios de operador y transiciones de otro estado a `Escalado`.
La asignación debe ser nula o apuntar a una cuenta con rol `operador` activa.
Reabrir con un operador inactivo se rechaza con SQLSTATE `23514`: el llamador
debe indicar otro operador activo o quitar la asignación en la misma operación.
No se libera automáticamente un reclamo histórico por cambiar otros campos ni
por ejecutar `SET estado=estado` cuando aún no está escalado.

Antes de aplicar, comprobar si el fallo ya dejó asignaciones inválidas. Esta
consulta solo devuelve un conteo, sin datos personales:

```sql
select count(*) as escalados_con_operador_invalido
from public.reclamos r
where r.estado = 'Escalado' and r.operador_asignado_id is not null
  and not exists (
      select 1 from public.usuarios u
      where u.id = r.operador_asignado_id and u.rol = 'operador' and u.activo
  );
```

La migración repite esa comprobación bajo el bloqueo de tabla obtenido al
recrear el trigger. Si hay resultados, aborta y revierte todos sus cambios:
no modifica asignaciones existentes. Revisar su tratamiento con el responsable
y ejecutar `ROLLBACK` si el cliente dejó abierta la transacción fallida.

La operación es transaccional, con espera de bloqueo de 5 segundos y límite de
30 segundos por sentencia. Conserva `SECURITY INVOKER`, `search_path` vacío y
la revocación de ejecución a roles públicos. No cambia RLS ni los permisos de
tablas. `FOR SHARE` sigue serializando la validación con la baja del operador.

Tras aplicarla, comprobar la definición instalada de función y trigger,
permisos y el conteo anterior; ejecutar las pruebas PostgreSQL autorizadas de
reapertura válida/inválida, historial y ambos órdenes de concurrencia con la
baja. No confundir los controles de texto locales con pruebas SQL reales.
Detalles y resultados en `docs/hu7_validacion_supabase.md`.
