# HU7 / AARI-79 — aplicación y validación en Supabase

## Resultado y alcance

El 02/09/2026, con autorización explícita del responsable, se aplicó
`backend/migrations/17_usuarios_operadores.sql` al proyecto compartido AARI de
desarrollo (`kmisxmwrqthqkrbsqcfq`, PostgreSQL 17.6). Durante las pruebas de base
de datos no se enviaron correos reales; la prueba SMTP posterior se detalla abajo.

- Rama: `codex/AARI-79-gestion-operadores`, base `main` en `b592421`.
- Historial de Supabase: versión `20260902235524`, nombre `hu7_usuarios_operadores`.
- SHA-256 del archivo aplicado (bytes locales):
  `1A9F7AF7D0FF55568178D9DFD845C184917EF901C80F2E92098D2632AE32046A`.
- Las pruebas de Supabase y SMTP se realizaron antes de publicar el código.
  El 03/09/2026 el responsable autorizó commit, push y PR de esta rama para
  revisión. No se autorizó el cierre de Jira ni una nueva carga de tiempo.

## Qué cambia

La migración agrega `usuarios.nombre_completo` (obligatorio y validado para
operadores), `reclamos.operador_asignado_id`, su FK e índice, y un trigger que
rechaza nuevas asignaciones a cuentas inactivas o de otro rol. La función usa
`SECURITY INVOKER`, nombres de tabla calificados y `search_path` fijo.

Mantiene RLS y revoca permisos del Data API a `anon` y `authenticated` sobre
usuarios/reclamos, además de no permitirles ejecutar la función de asignación.
El acceso funcional continúa por FastAPI y la conexión privada del backend.
No se agregan dependencias ni variables al `.env` de la aplicación.

Se añadieron límites locales de espera: `lock_timeout=5s` y
`statement_timeout=30s`. No modifican la configuración global de Supabase.

## Comprobaciones antes y después

Antes se confirmó el proyecto, la ausencia de operadores antiguos y de los
campos de HU7, y la disponibilidad de `pgcrypto` en `extensions`. Los asesores
de seguridad/rendimiento se consultaron para contar con una referencia previa.

Después se verificaron columnas, restricción de nombres, FK, índice, trigger,
configuración de la función, RLS y ausencia de permisos de los roles públicos.
El historial confirmó la versión aplicada. Los conteos permanecieron iguales:

| Registro | Antes | Después de migrar y probar |
| --- | ---: | ---: |
| Usuarios | 6 | 6 |
| Reclamos | 0 | 0 |
| Entregas de credenciales | 5 | 5 |
| Operadores | 0 | 0 |

No quedaron usuarios/personas/especialidades sintéticos ni esquemas
`aari_hu7_test_*`. Los datos funcionales se revirtieron mediante rollback;
el esquema privado y sus copias vacías se eliminaron al finalizar las pruebas.
No se eliminaron ni cambiaron registros de los integrantes del proyecto.

## Pruebas PostgreSQL reales

Archivo: `backend/tests/test_operadores_supabase_integration.py`.
Resultado: **6 aprobadas**, sin SMTP real.

1. Alta con correo simulado fallido, hash `pgcrypto`, unicidad global,
   regeneración de clave, primer ingreso/cambio de contraseña, listado y baja.
2. FK y trigger reales de asignación, liberación de escalados, conservación de
   resueltos, idempotencia y rollback conjunto de la cuenta y sus asignaciones.
3. Nombres inválidos, nombre Unicode con guion, y permisos de tablas/función.
4. Reintento concurrente que espera el bloqueo y rechaza una cuenta que acaba
   de completar el primer ingreso.
5. Asignación concurrente que espera una desactivación y luego la rechaza.
6. Desactivación que espera una asignación en curso y después libera ese reclamo.

Los primeros tres casos usan las tablas reales dentro de una transacción externa
con savepoints (`join_transaction_mode="create_savepoint"`) y rollback final.
Los casos concurrentes usan conexiones independientes sobre copias **sin datos**
de usuarios, entregas y reclamos en un esquema privado único. Reutilizan el SQL
del repositorio y una copia de la función instalada, cambiando solo su esquema;
la FK del operador también se reproduce allí. Las demás relaciones de reclamos
se validan en los casos funcionales sobre `public`, no en esas copias.

### Repetir solo con autorización

Desde `backend/`, con `DATABASE_URL` del entorno de desarrollo en el `.env` local,
se habilita exclusivamente esta suite. Nunca compartir la URL ni contraseñas en
el comando, documentación o mensajes. El test comprueba que la conexión coincida
con el proyecto confirmado y no ejecuta migraciones sobre `public`.

```powershell
$env:RUN_OPERADORES_POSTGRES_TESTS = '1'
$env:SUPABASE_TEST_PROJECT_REF = 'kmisxmwrqthqkrbsqcfq'
try {
    .\.venv\Scripts\python.exe -m pytest tests/test_operadores_supabase_integration.py -q --tb=no -p no:cacheprovider
} finally {
    Remove-Item Env:RUN_OPERADORES_POSTGRES_TESTS -ErrorAction SilentlyContinue
    Remove-Item Env:SUPABASE_TEST_PROJECT_REF -ErrorAction SilentlyContinue
}
```

La suite necesita permiso para crear y eliminar su esquema privado temporal.
No usa datos reales para comprobar concurrencia. Ante una interrupción forzada,
revisar si quedó un esquema de prueba y confirmar su propiedad antes de borrarlo;
no eliminar esquemas mediante un comodín. `--tb=no` evita imprimir parámetros o
detalles de filas si una comprobación falla.

Regresión posterior con PostgreSQL deshabilitado y `DATABASE_URL=sqlite://`:
**206 aprobadas, 8 omitidas** (6 son los casos externos anteriores y 2 existentes),
2 advertencias de deprecación. Comando: `python -m pytest tests -q -p no:cacheprovider`
con un `--basetemp` nuevo para evitar los permisos del temporal predeterminado.
La validación previa del frontend se mantiene: 73 pruebas, lint y build correctos;
no hubo cambios de frontend durante esta etapa.

## Prueba SMTP autorizada del 02/09/2026

Se envió un único correo técnico con asunto `AARI - Prueba de correo HU7` al
destinatario indicado por el responsable, usando la configuración SMTP del
`.env` local, autenticación y STARTTLS con validación de certificado. El servidor
SMTP aceptó el mensaje sin rechazar al destinatario. La recepción en la bandeja
de entrada o Spam sigue pendiente de confirmación del responsable.

La consulta previa detectó que el correo indicado ya pertenece a una cuenta
activa de propietario que completó su primer ingreso. Para preservar esa
identidad, no se creó un operador ni se cambió su contraseña, rol o estado.
El mensaje identifica claramente su carácter técnico y no contiene credenciales.
Esta prueba valida el canal SMTP, **no el flujo completo de alta de operador**:
para ese recorrido hace falta acordar una dirección no registrada en el sistema.

No se modificó la configuración ni se registraron direcciones o secretos en
esta evidencia. `python-dotenv` advirtió sobre dos líneas no interpretables en
el archivo local (1 y 9); no impidieron cargar SMTP ni enviar la prueba. Queda
pendiente revisar su formato, sin exponer sus valores.

## Alta real de operador y correo autorizados del 02/09/2026

El responsable confirmó explícitamente la creación persistente de una cuenta
de prueba y el envío de su contraseña temporal a una segunda dirección, distinta
de la ya registrada como propietario. La comprobación previa confirmó que la
nueva dirección estaba disponible y que el backend apuntaba al Supabase AARI
de desarrollo. No se modificó la cuenta de propietario existente.

Se ejecutó una sola alta con `get_operadores_service().create(...)`, usando
`OperadorCreate`, el repositorio PostgreSQL y `SmtpWelcomeEmailSender` reales.
No se sustituyeron componentes por mocks. Se comprobó:

- Cuenta `Operador de prueba AARI` guardada, rol `operador` y `activo=true`.
- `primer_ingreso=true`, conservado para que el responsable cambie su clave.
- Hash bcrypt presente; sin contraseñas ni hashes en la respuesta pública.
- Entrega en estado `enviado`, un intento y fecha de envío registrada.
- Cuenta encontrada por el listado y búsqueda del servicio de operadores.

El correo lleva el asunto `Tus credenciales de acceso a AARI`. La aceptación
SMTP y el registro de entrega fueron correctos; no prueban por sí solos la
recepción en la bandeja del destinatario, que sigue pendiente de confirmación.
La prueba ejercitó el servicio de negocio, persistencia y correo: **no reemplaza
el recorrido manual por HTTP/interfaz ni el primer ingreso del responsable**.

Esta cuenta se conserva deliberadamente para la prueba manual autorizada; no es
un residuo de las pruebas PostgreSQL con rollback descritas anteriormente. No
se reenvió correo, rotó la clave ni desactivó la cuenta automáticamente. Las
direcciones y credenciales no se incluyen en esta evidencia. No se cambiaron
código de aplicación, dependencias, configuración ni migraciones en esta prueba.

## Asesores y pendientes de seguridad previos

Los asesores consultados después no reportaron hallazgos adicionales respecto
de la revisión previa. Esto **no significa que todo el proyecto carezca de
pendientes**. Ya existían:

- Cuatro advertencias por `search_path` mutable: `set_updated_at`,
  `chk_max_fotos_por_reclamo`, `chk_alerta_cancelaciones` y
  `log_cambio_estado_reclamo`.
  [Criterio y remediación de Supabase](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable).
- Dos advertencias por permisos de ejecución de `rls_auto_enable` como
  `SECURITY DEFINER` para
  [anon](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
  y [authenticated](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).
- Avisos informativos de RLS sin políticas, coherentes con tablas consumidas
  exclusivamente desde el backend. No agregar políticas públicas solo para
  silenciarlos. [Referencia](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy).
- Avisos de [FK sin índice](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys)
  y [índices aún sin uso](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index)
  anteriores a HU7; la nueva FK sí tiene índice.

Estos objetos ajenos no se modificaron. Su revisión debe acordarse como trabajo
separado, especialmente las funciones compartidas con otros módulos.

## Qué debe hacer Talía y qué falta

- En el mismo Supabase de AARI **no repetir la migración 17**: ya está aplicada
  una vez para el equipo. La corrección 18 descrita abajo también se aplicó con
  autorización el 03/09/2026: no repetirla. En otra base, seguir la guía y sus controles.
- Obtener el código cuando se publique la rama/PR y, después de la revisión y
  merge, actualizar `main`. La migración no hace pull ni publica el código.
- Mantener el `.env` local existente: se reutilizan SMTP y APP_LOGIN_URL de HU6.
- Confirmar la recepción del correo de credenciales de la cuenta de operador
  creada con autorización. Quedan el primer ingreso/cambio de contraseña y la
  prueba manual de la interfaz; después, revisión de Talía y PR autorizado.

## Validación previa a publicación del 03/09/2026

Se confirmó que la rama de HU7 parte del `main` remoto actualizado en `b592421`.
La revisión del alcance mantiene los cambios limitados a operadores, su
integración en rutas/navegación y el ajuste accesible del diálogo compartido.

- Backend: `python -m pytest tests -q --tb=short -p no:cacheprovider --basetemp
  <directorio_temporal_nuevo>`, con `DATABASE_URL=sqlite://` y las tres suites
  externas deshabilitadas: **206 aprobadas, 8 omitidas y 2 advertencias** ya
  descritas. No se repitieron pruebas de Supabase ni SMTP.
- Frontend: `npm run lint`, `npm test` y `npm run build` correctos;
  **73 pruebas aprobadas en 19 archivos**.
- Verificación de formato mediante `git diff --check` y revisión de secretos
  antes del commit. Los `.env`, logs y artefactos de ejecución quedan fuera.

La publicación no equivale a un merge ni al cierre de la historia. La confirmación
específica de recepción y primer ingreso del responsable no se presupone por
la autorización del PR; esos pendientes permanecen indicados en esta evidencia.

## Corrección de reapertura del PR #21 (03/09/2026)

El responsable aprobó implementar la corrección propuesta tras el
[hallazgo de revisión](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/21#issuecomment-5533304112).
La migración 17 solo dispara el trigger al insertar o escribir el operador;
un cambio únicamente de estado podía reabrir un reclamo con operador inactivo.

Se preparó `18_revalidar_operador_al_escalar.sql` en la misma rama del PR,
**sin modificar 17**. Su aplicación al Supabase compartido fue autorizada y
se detalla en el apartado siguiente. Cambia tanto las columnas del trigger como
la condición interna de su función. Se mantienen
el bloqueo `FOR SHARE`, `SECURITY INVOKER`, `search_path` fijo y permisos privados.
Se rechaza la reapertura inválida; se permite otro operador activo o asignación
nula en esa operación. No se opta por desasignar silenciosamente ni reescribir
historial. Un control transaccional aborta ante escalados inválidos existentes,
sin intentar corregir datos reales automáticamente.

Pruebas agregadas:

- Cuatro controles estructurales locales de transacción, condiciones, permisos
  y revisión de datos previos. **No ejecutan SQL ni demuestran bloqueos reales.**
- Ocho casos PostgreSQL de reapertura desde `Resuelto` y `Reabierto por
  disconformidad`: operador inactivo, activo, reemplazo activo y sin asignación.
  Verifican la conservación de asignación histórica y el rollback del historial
  cuando se rechaza la operación.
- Dos casos concurrentes: reapertura que espera una baja y es rechazada;
  baja que espera una reapertura válida y después libera ese escalado.
- La réplica concurrente obtiene ahora la función **y el trigger** instalados
  mediante `pg_get_functiondef` y `pg_get_triggerdef`, sin columnas codificadas
  manualmente que pudieran ocultar una regresión.

Las pruebas externas requieren autorización y la migración 18 instalada. Durante
la preparación local se comprobó que la carpeta de PostgreSQL no tenía binarios
ejecutables; no se instaló una
dependencia ni se recurrió a Supabase sin permiso para suplirla. La CLI de
Supabase tampoco está disponible; el archivo mantiene la convención incremental
numerada del repositorio y se preparó con edición local.

Validación de esta corrección:
`python -m pytest tests -q --tb=short -p no:cacheprovider --basetemp <directorio_temporal_nuevo>`,
con `DATABASE_URL=sqlite://` y las suites externas deshabilitadas:
**210 aprobadas, 18 omitidas y 2 advertencias preexistentes**.
Las 18 omisiones incluyen los 16 casos optativos de operadores
y dos suites externas previas. No se volvió a ejecutar el frontend porque no
se modificó. `git diff --check` sin errores y migración 17 sin diferencias.

La aplicación y validación posteriores se registran a continuación. Queda obtener
nueva revisión de Talía antes de fusionar.
No se envían correos, no se cierra Jira y no se registra tiempo de esta corrección
sin la confirmación del tiempo real del responsable.

## Aplicación autorizada de la migración 18 (03/09/2026)

El responsable autorizó aplicar 18, ejecutar las pruebas reales sin SMTP y
publicar la corrección si las validaciones resultaban correctas. Se confirmó
el proyecto AARI `kmisxmwrqthqkrbsqcfq`, activo y con la 17 instalada. El control
previo no encontró reclamos escalados con operador inválido ni esquemas de
prueba pendientes. No se modificaron asignaciones ni cuentas reales.

- Historial: `20260904001512_hu7_revalidar_operador_al_escalar`. La versión está
  en UTC; la aplicación ocurrió el 03/09/2026 a las 21:15 en Argentina.
- SHA-256 del archivo aplicado (bytes locales):
  `0005DF1392FC62E33877C72629665F7B984F102679CAC6EBAACE98E6A165BA0E`.
- Función y trigger instalados verificados: incluye la columna `estado` y
  revalida la entrada a `Escalado`; `SECURITY INVOKER`, `search_path` vacío y
  ausencia de ejecución pública conservados.
- La 17 conserva su hash original y no se volvió a ejecutar.

### Pruebas, limpieza y seguridad posteriores

Con `RUN_OPERADORES_POSTGRES_TESTS=1` y el proyecto explícitamente confirmado,
se ejecutó desde `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_operadores_supabase_integration.py -q --tb=no -p no:cacheprovider --basetemp <directorio_temporal_nuevo>
```

Resultado: **16 aprobadas**. Incluye los ocho casos de reapertura y cinco
escenarios concurrentes (dos nuevos), además de los tres casos funcionales
originales. No hubo SMTP real: el emisor está simulado. Los casos sobre `public`
se revirtieron, y el esquema privado exacto de concurrencia se eliminó al
finalizar. No se copiaron datos reales a ese esquema.

Comprobación independiente después de las pruebas: 7 usuarios, 0 reclamos,
6 entregas y 1 operador, igual que antes. Cero usuarios sintéticos de la suite,
cero esquemas `aari_hu7_test_*` y cero escalados inválidos. La cuenta de prueba
persistente previamente autorizada se conserva; no se confundió con los datos
transitorios ni se modificó.

RLS habilitada y sin permisos de lectura/escritura para `anon` y `authenticated`
en usuarios/reclamos. Los asesores no reportaron hallazgos nuevos: seguridad
conserva 27 avisos (incluidas las 6 advertencias previas documentadas arriba);
rendimiento pasó de 23 a 22 avisos informativos, sin incorporaciones.
No se modificaron funciones o índices ajenos a la corrección.

Regresión local final con SQLite y las suites externas deshabilitadas:
**210 aprobadas, 18 omitidas y 2 advertencias previas**. Comando idéntico al de
la preparación local, usando un directorio temporal nuevo. La revisión de
formato y secretos del diff no detectó errores ni credenciales reales.

La corrección se entrega para nueva revisión en el PR #21. La publicación no
autoriza merge, cierre de Jira ni tiempo adicional; esos pasos siguen sujetos
a la indicación del responsable.

## Fuentes técnicas consultadas

- [Columnas y condiciones de triggers en PostgreSQL 17](https://www.postgresql.org/docs/17/sql-createtrigger.html).
- [Triggers de PostgreSQL en Supabase](https://supabase.com/docs/guides/database/postgres/triggers).

- [Permisos del Data API y RLS](https://supabase.com/docs/guides/api/securing-your-api).
- [Cambio de exposición automática de tablas](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically):
  se conserva el acceso por conexión directa del backend y se revocan permisos explícitamente.
- [Transacciones externas y savepoints para pruebas en SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites).
