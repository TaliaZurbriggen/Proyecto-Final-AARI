# HU16 — Autorización de gasto extraordinario (AARI-180)

## Alcance y estado

Propuesta aprobada el 15/10/2026. Implementación en
`codex/AARI-180-autorizacion-gasto`, desde main `02479b9`, en checkout aislado.
HU y subtareas AARI-181 a AARI-190 En curso. Commit, push y PR autorizados el
16/10/2026 para revisión de Talía. Sin autorización de merge, cierre ni nuevos
worklogs; el tiempo real requiere confirmación humana.

La integración completa de coordinación NO forma parte de esta entrega:
AARI-345 conserva AARI-236/AARI-237 pendientes. El PR #34 de HU21 se conserva
sin merge por nuestra parte. HU16 puede funcionar con el esquema de main;
no importa ni depende del código no integrado de HU21 ni del trabajo de Talía.

## Recorrido implementado

1. La clasificación extraordinaria existente registra al propietario como
   responsable y encola el aviso con enlace autenticado a la decisión.
2. El propietario ingresa a **Autorizaciones** en la navegación superior o
   desde su inicio. Ve únicamente gastos extraordinarios de sus propiedades,
   paginados de a 20. El detalle muestra clasificación, plazo e historial.
3. Autorizar registra `Autorizado`. La pantalla aclara que la elección del
   proveedor es el paso pendiente de HU17: no simula su implementación.
4. Rechazar requiere confirmación, registra `Rechazado por propietario` y
   cierra este ciclo. Se conserva el historial y se libera la restricción de
   reclamo activo para permitir otro problema en la misma unidad. Tampoco
   cuenta como activo en el resumen administrativo.
5. La transición, auditoría y notificaciones se confirman juntas. El trigger
   existente encola el aviso al inquilino y se encola el aviso al operador
   activo, con respaldo administrativo según las reglas existentes.
6. Se reutiliza el job de HU12: recordatorio a las 48h y vencimiento 24h después
   (72h totales por defecto). Se respetan los plazos persistidos/configurados.
   Para este circuito el estado vencido es `Pendiente de autorización - vencido`;
   los demás responsables conservan el vencimiento genérico.

El correo se entrega fuera de la petición por el outbox existente. Un fallo
SMTP no revierte la decisión. No se envían correos en las pruebas automatizadas.
Los pedidos iniciales/recordatorios obsoletos se cancelan para no reintentarlos
tras decidir o vencer. Un mensaje que SMTP ya aceptó no puede retirarse;
no se afirma entrega exactamente una vez.

## API y seguridad

- `GET /propietario/reclamos?page=1`: listado del propietario autenticado.
- `GET /reclamos/{uuid}/autorizacion`: detalle limitado al mismo propietario.
- `POST /reclamos/{uuid}/autorizar` y `POST /reclamos/{uuid}/rechazar`:
  `request_id` UUID y `expected_updated_at` con zona horaria, sin campos de
  identidad del cliente. Campos adicionales se rechazan.
- Rol propietario, cuenta activa y primer ingreso completado. El vínculo
  usuario/perfil/propiedad se revalida en la transacción. No basta conocer un UUID.
- La titularidad se mantiene con bloqueos compartidos; reclamo/responsable se
  bloquean antes de decidir. Sólo una de dos decisiones concurrentes gana.
- Versión vieja, estado incorrecto o plazo alcanzado: 409 sin mutaciones.
- El mismo UUID/payload devuelve el resultado original sin repetir efectos.
  Cambiar decisión/payload o reutilizarlo en otro reclamo no ejecuta otra acción.
- La auditoría conserva usuario, nombre del propietario al decidir, instante,
  solicitud de autorización y referencia al historial. No incluye contraseñas.

## Migración aplicada en desarrollo

`20261015212745_hu16_autorizacion_gasto.sql`, generado por la CLI oficial
Supabase 2.81.3. Se conserva la estructura `backend/migrations/` del repositorio.

Agrega `reclamo_autorizaciones` con unicidad por evento y por reclamo/solicitud,
FK indexadas, comprobación decisión/estado y RLS; revoca acceso a public,
anon y authenticated. No expone una API pública ni agrega políticas permisivas.
Recrea el índice de reclamo activo excluyendo también el rechazo terminal.
No elimina ni actualiza datos de negocio; DDL transaccional, lock timeout 5s
y statement timeout 30s. Requiere esquema integrado de main y HU12/outbox.

**16/10/2026: aplicada con autorización al Supabase AARI compartido de desarrollo**,
PostgreSQL 17.6, historial `20261016053335_hu16_autorizacion_gasto`.
El archivo local conserva la versión generada por CLI `20261015212745`;
la versión del historial fue asignada por `apply_migration`. Conservar ambas
referencias sin renombrar el archivo ni volver a ejecutarlo por integrante,
pull o cambio de rama.

Antes de aplicar se verificaron el proyecto, historial, dependencias, columnas,
triggers, índice anterior, ausencia de instalación parcial y cero claves
duplicadas para el índice nuevo. El DDL aprobado se ejecutó mediante
`apply_migration`, dentro de un bloque atómico con guardas de privacidad,
estructura y conservación de datos/permisos/secuencia. Ante una diferencia,
la operación aborta. No se agregaron funciones persistentes ni fixtures.

Verificación posterior independiente por MCP:

- Las **38 tablas existentes** (`public` y `aari_coordinacion`, 58 filas en
  total) conservaron conteos y huellas, además de RLS, ACL y políticas.
- La secuencia visible del reclamo conservó su valor, sin consumir numeración.
- Tabla nueva vacía, 10 columnas no nulas, tres FK validadas, dos CHECK,
  PK, unicidad por solicitud y cuatro índices válidos/listos.
- RLS habilitado; cero políticas y permisos de tabla/columnas revocados a
  `anon` y `authenticated`; cero privilegios para PUBLIC. Acceso sólo a través
  del backend autorizado, no desde clientes del Data API.
- Índice de reclamo activo único, válido/listo, con el rechazo terminal excluido.
- Historial de migración confirmado. Sin decisiones nuevas, cambios de estado,
  notificaciones encoladas, correos, workers activados ni worklogs.

El primer intento del conector expiró antes de aplicar. Se comprobó por lectura
que tabla e historial seguían ausentes y el índice intacto antes de reintentar
una sola vez; la segunda aplicación y su lectura de verificación fueron correctas.
No se modificó `.env` real ni se agregaron claves, dependencias de aplicación o
variables nuevas. Usa `APP_LOGIN_URL`, SMTP y worker existentes.

### Asesores de seguridad y rendimiento

No se introdujeron advertencias nuevas ni FK sin índice. Los avisos nuevos
son informativos y esperables: [RLS sin políticas](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
en la tabla privada y [dos índices todavía sin uso](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).
No agregar políticas permisivas ni borrar índices de FK para silenciarlos.

Se conservaron los avisos previos de `set_updated_at`
([search_path mutable](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable))
y `rls_auto_enable` (SECURITY DEFINER ejecutable por
[anon](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
y [authenticated](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)),
así como las 16 FK anteriores sin índice. Quedan fuera de esta migración;
su corrección requiere revisión y alcance específico, no se declaran resueltas.

## Interfaz y pruebas

Se reutilizan PageContainer, PageHeading, Button, ConfirmDialog, StatusBadge,
AlertMessage, LoadingState y EmptyState, con tokens y CSS Modules de AARI.
Una navegación superior; en móvil se apilan acciones y columnas. Rechazo por
teclado con foco de cancelación; durante el guardado ambas acciones se bloquean.
Ante respuesta perdida se reutiliza el UUID y sólo permite reintentar la misma
decisión. Ante 409 se actualiza el detalle antes de volver a ofrecer acciones.

Validación visual sobre componentes reales y API simulada con datos ficticios:
escritorio y 390px, sin desbordamiento horizontal, botones táctiles de 44px.
La vista temporal está ignorada en Git y NO es una ruta de producción. Esta
revisión visual no se presenta como flujo real de login/correo/Supabase.

Comandos de validación (desde backend/frontend según corresponda):

```text
python -m pytest -q -x -p no:cacheprovider --tb=short --basetemp=artifacts/hu16-focused-final tests/test_expense_authorizations.py tests/test_expense_authorizations_postgres.py tests/test_responsible_actor_postgres.py
python -m pytest -q -x -p no:cacheprovider --tb=short --basetemp=artifacts/hu16-regression-final --ignore=tests/test_provider_candidates_volume_postgres.py
npm run lint
npm run test -- --reporter=dot
npm run build
```

PostgreSQL se ejecuta sólo en loopback y con bases descartables/roles ficticios.
Workers, SMTP y pruebas externas permanecen desactivados. La primera ejecución
aislada de Windows bloqueó sockets locales; se repitió fuera del aislamiento.
Una regresión inicial encontró permisos antiguos en la carpeta temporal global
de pytest; la repetición usa una carpeta nueva dentro del proyecto. Una pasada
previa detectó una aserción de HU12 que esperaba el vencimiento genérico para
el propietario; se ajustó al estado específico aprobado de HU16 y se repitió.
No se contabilizan corridas fallidas/interrumpidas como aprobadas.

Resultados finales del 15/10/2026:

- Backend: **940 aprobadas / 51 omitidas**, 243,71 s, PostgreSQL 17.11 local.
  Incluye las 28 pruebas nuevas de HU16. Se omitieron pruebas externas por sus
  guardas; no se repitió el archivo de volumen de HU15, sin cambios en esa HU.
  Las 18 advertencias son del adaptador datetime SQLite/Python 3.12 preexistente.
- Pasada focalizada previa: 40 aprobadas (41,19 s), HU16 más regresiones HU12;
  no se suman al total anterior.
- Frontend: **341 aprobadas / 37 archivos**, 65,82 s; incluye 9 casos nuevos.
  `npm run lint` y `npm run build` correctos (build 2,30 s).
- API HTTP con repositorio/PostgreSQL reales e identidad de prueba inyectada;
  no acredita cookies/login real ni Supabase compartido.
- Concurrencia entre decisiones opuestas y entre reintentos del mismo evento,
  auditoría única, rechazo terminal, versión obsoleta, cuenta inactiva, permisos,
  vencimiento y recordatorio idempotentes, rollback y fallo SMTP simulado.
- Revisión visual escritorio/móvil con componentes reales y API simulada;
  no representa un flujo end-to-end contra servicios externos.
- `pip check`, revisión de diff/formato y patrones de secretos correctos.
- Cero bases ficticias remanentes en el clúster usado por la suite. PostgreSQL
  y la vista Vite temporal de QA detenidos; runtime y archivos locales de QA
  preservados e ignorados por Git. No se apagaron servicios de la aplicación
  del usuario ni se borraron sus datos.

Para repetir la suite se requiere un PostgreSQL local dedicado mediante
`AARI_TEST_POSTGRES_URL`, nunca la conexión compartida. Usar `DATABASE_URL=sqlite://`,
`NOTIFICATION_WORKER_ENABLED=false`, `CONTRACT_ANALYSIS_WORKER_ENABLED=false`,
`PROVIDER_CANDIDATES_WORKER_ENABLED=false` y `SMTP_HOST` vacío. Elegir una carpeta
`--basetemp` nueva: pytest elimina la indicada al iniciar. No reutilizar una
carpeta con datos ajenos.

Verificación previa a publicación del 16/10/2026, sin cambios productivos:

- `python -m pytest -q -p no:cacheprovider --tb=short tests/test_expense_authorizations.py tests/test_responsible_actor_notifications.py tests/test_admin_home.py`:
  72 aprobadas, 0,79 s, SQLite/mocks y servicios externos desactivados.
- `npm run test -- src/features/reclamos/pages/OwnerExpenses.test.jsx --reporter=dot`:
  9 aprobadas, 50,81 s; `npm run lint` y `npm run build` correctos (2,49 s).
- No se suman a las pasadas completas del 15/10 ni se presentan como una
  nueva ejecución de PostgreSQL o del flujo compartido. Asesores revisados
  nuevamente: los mismos avisos documentados, sin advertencias propias de HU16.
- Diff limitado a 24 archivos HU16; sin `.env`, artefactos de QA, dependencias
  nuevas ni cambios del checkout principal.

## Pendientes de aceptación

- Prueba humana del portal no realizada: la app se abrió con backend/base
  conectados, pero no había solicitudes extraordinarias para decidir y no se
  crearon fixtures compartidos. No se presenta como validación aprobada.
- Envío real SMTP sólo con autorización específica.
- La verificación compartida de esta entrega fue de esquema/lecturas, no una
  prueba de escritura funcional de decisiones ni de entrega de correos reales.
- Publicación autorizada para revisión de Talía; merge y cierre pendientes.
- HU17 y la integración end-to-end AARI-345 conservan su alcance pendiente.
- Registrar tiempo real únicamente cuando la persona responsable lo confirme.
## Nota de integración HU17 (18/10/2026)

La rama dependiente `codex/AARI-191-eleccion-proveedor` implementa la
continuación automática autorización → elección, la etapa persistida con plazos
nuevos y pruebas de integración. Esta ampliación y su migración se documentan en
[HU17](hu17_eleccion_proveedor.md). El contenido siguiente describe la entrega
base HU16 del PR #35; no implica que dicho PR ya incluya los cambios de HU17.
No cerrar AARI-184 ni declarar fusionadas ambas historias antes de su revisión.
