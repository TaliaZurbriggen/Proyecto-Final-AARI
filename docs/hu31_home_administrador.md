# HU31 / AARI-332 — Home del administrador

**Fecha:** 05/10/2026

**Estado:** implementación validada; pendiente de conectar HU13, revisión y PR.

**Rama:** `codex/AARI-332-home-administrador`

**Base:** `origin/main` en `80afb67`, con el merge de HU11.

**Jira:** HU y subtareas AARI-333 a AARI-337 en curso. Se registraron 2h reales autorizadas; sin cambiar la estimación original del Sprint.

**Publicación:** commit y push autorizados el 05/10/2026; el cierre y el merge no están autorizados en esta instancia.

## Objetivo y alcance aprobado

Un punto de entrada para que administración conozca la situación operativa y
continúe sus tareas. Se implementa la variante **Operativo** aprobada: dos
resúmenes de reclamos, una región con cinco módulos y accesos a contratos e
historial. No es el dashboard analítico de HU26: no hay gráficos, tendencias,
predicciones ni comparaciones por período.

Al entrar con rol administrador se dirige a `/inicio`. La identificación usa
la sesión existente. El primer ingreso exige cambiar la contraseña antes de
ver el Home. Los portales de operador, propietario e inquilino se conservan;
ni la ruta ni el endpoint del resumen están habilitados para esos roles.

## Decisiones y alternativas

### Navegación compartida

El equipo eligió tarjetas compactas y redondeadas en escritorio y un menú
desplegable en móvil. Se implementan en la misma cabecera administrativa y
con una única navegación, no como una barra lateral ni como menús duplicados.
El desplegable indica el módulo actual y se cierra al elegir una opción,
pulsar fuera o presionar Escape; Escape devuelve el foco a su botón.

Se aplica la skill `.agents/skills/aari-frontend`: tokens de la paleta,
Inter, CSS Modules, iconos Lucide y componentes existentes. La variante de
pestañas sigue disponible para los demás layouts. El Home no presenta un
buscador global ni una campana sin comportamiento propio; los módulos
conservan sus controles actuales.

### Contadores reales y consistentes

`GET /admin/resumen` es de solo lectura y reutiliza `require_admin`.
Obtiene todos los agregados con **una sola sentencia SQL**, para que compartan
la instantánea de la consulta. No obtiene listados completos ni suma páginas
del frontend. Los agregados tampoco multiplican proveedores por coberturas o
reclamos por relaciones asociadas. No se añaden tablas ni migraciones.

| Dato | Regla aplicada |
|---|---|
| Propietarios, propiedades e inquilinos | Total de registros de cada tabla, no solamente registros activos. |
| Proveedores | Total registrado y subconjunto con `activo = true`. |
| Operadores | Usuarios con `rol = 'operador'`, más su subconjunto activo; no cuenta administradores. |
| Reclamos activos | Todos salvo `Resuelto` y `Resuelto (sin confirmación)`, según la regla ya usada en el alta de reclamos. Un reabierto sigue activo. |
| Pendientes de clasificación | Estado `Escalado` o `Clasificación pendiente`, sin `tipo_gasto`, sin origen de decisión `operador`/`administrador` y sin fila en `reclamo_responsables`. |

Los pendientes de clasificación **están incluidos** en los activos; no se
suman para obtener otro total. Se excluyen los escalados de etapas posteriores
que ya tienen clasificación o solicitud de responsable. La regla coincide
con la cola de clasificación prevista en HU13, no con una cola general de
todas las incidencias posibles.

La respuesta incluye `consultado_en` con zona horaria. La interfaz presenta
la fecha y hora mediante `America/Argentina/Buenos_Aires`, independientemente
de la zona horaria del servidor o del navegador.

### Actualización, carga y errores

Se consulta al entrar y al pulsar **Actualizar**. No hay sondeo periódico.
Mientras se carga, el botón está deshabilitado y los contadores muestran `—`.
Una base vacía correctamente consultada muestra cero y una invitación a
registrar datos. Un fallo, una respuesta incompleta o contadores incoherentes
no se convierten en cero: se retiran los valores anteriores, se informa el
error y se permite reintentar, manteniendo los accesos a los módulos.

Al salir se cancela la solicitud; una respuesta atrasada no reemplaza la
información de una pantalla nueva. El backend no expone detalles SQL ni de
conexión cuando el repositorio falla: responde HTTP 503 con un mensaje seguro.

### Integración pendiente con HU13

Al crear esta rama, HU13 aún no estaba fusionada en `main`. La persona
responsable aprobó explícitamente continuar y completar su conexión después.
Por eso **Revisar casos** permanece deshabilitado, con una explicación, y no
se publica un enlace hacia una ruta inexistente. No se incorpora ni se
cherry-pickea trabajo de la rama de HU13.

El historial sí tiene acceso funcional: **Buscar propiedad** abre el listado
de propiedades, desde donde la ficha permite ir al historial de HU11. No se
crea un listado global de reclamos en esta HU. Contratos abre el módulo de HU29.

## Componentes principales

- `backend/app/api/admin_home.py`: endpoint privado y error seguro.
- `backend/app/db/admin_home.py`: agregación SQL del resumen.
- `backend/app/schemas/admin_home.py`: contrato tipado, contadores no negativos
  y validación de subconjuntos.
- `backend/app/main.py`: registro del router, sin alterar los anteriores.
- `frontend/src/features/home/`: API, pantalla operativa, estilos y pruebas.
- `frontend/src/features/auth/routing.js` y `frontend/src/App.jsx`: destino
  inicial y ruta protegida.
- `frontend/src/layouts/AdminLayout.jsx` y `components/layout/AppHeader.*`:
  navegación responsive compartida y acceso Inicio.

## Validaciones realizadas

Todas las validaciones de esta ejecución son locales. No se consultó ni
modificó Supabase, ni se consumió Gemini, Storage o SMTP reales. No se instalaron
dependencias. La base de prueba PostgreSQL fue creada con datos ficticios y
eliminada al terminar por el fixture de prueba.

| Validación | Resultado |
|---|---|
| Backend completo, servicios externos deshabilitados | **392 passed, 40 skipped**. |
| Backend focalizado `tests/test_admin_home.py` | **50 passed**. Incluido también en la suite completa. |
| PostgreSQL local `tests/test_admin_home_postgres.py` | **1 passed** contra PostgreSQL 17 y esquema creado con migraciones reales. |
| Frontend completo | **140 passed** en 29 archivos. |
| Lint y build frontend | Aprobados. |
| Navegador Chrome aislado | Aprobado en 1440, 1024, 768, 390 y 320 px; sin desborde horizontal. |

La prueba de PostgreSQL comprueba base vacía, totales, proveedores con varias
coberturas sin duplicación, exclusión de administradores, estados y orígenes
de reclamos, exclusión por solicitud de responsable y valores actualizados
después de cambios. Reutiliza el fixture local de HU12, que solo permite una
instancia en localhost y crea/elimina una base aleatoria aislada.

La prueba visual usa la aplicación compilada con respuestas HTTP sintéticas,
no una maqueta estática. Verifica navegación móvil y regreso, foco visible,
Escape, áreas táctiles, carga, base vacía, fallos sin datos viejos, reintento
y ausencia de errores JavaScript. Las capturas locales de QA se conservan en
`backend/artifacts/hu31/` (ignorado por Git), sin datos personales reales.

Las pruebas de rutas y endpoint incluyen sesión ausente, otros tres roles,
primer ingreso obligatorio y cuenta inactiva. Las pruebas frontend verifican
formato argentino, credenciales de sesión, accesos, respuestas inválidas y
cancelación de solicitudes.

En la suite backend quedaron 40 pruebas optativas omitidas por no habilitar
sus entornos externos o PostgreSQL dedicado. Se ejecutó por separado la
prueba PostgreSQL de HU31. Los avisos de deprecación de Starlette/httpx y del
adaptador datetime de SQLite ya existentes no impidieron la ejecución. El
build mostró un aviso de temporización de plugins de Vite, sin error de
compilación.

### Comandos reproducibles

Desde `backend/`, con dependencias ya instaladas, deshabilitar la carga del
`.env` local para evitar contactos involuntarios con servicios reales:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:DATABASE_URL='sqlite://'
$env:RUN_SUPABASE_INTEGRATION='0'
$env:RUN_CONTRATOS_POSTGRES_TESTS='0'
$env:RUN_OPERADORES_POSTGRES_TESTS='0'
$env:RUN_SUPABASE_MIGRATION_TESTS='0'
$env:RUN_HU12_SMTP_INTEGRATION='0'
$env:AARI_TEST_POSTGRES_URL=''
$env:NOTIFICATION_WORKER_ENABLED='false'
python -m pytest -q -p no:cacheprovider
python -m pytest -q tests/test_admin_home.py -p no:cacheprovider
```

Para la comprobación PostgreSQL, usar únicamente una instancia **local
dedicada**, con capacidad para crear bases y los roles locales `anon`,
`authenticated` y `service_role` sin login. No apuntar la variable a Supabase.
Configurar la URL local de prueba sin registrar su contraseña en documentación:

```powershell
# AARI_TEST_POSTGRES_URL: URL de la instancia local dedicada, configurada localmente.
python -m pytest -q tests/test_admin_home_postgres.py -p no:cacheprovider
```

Desde `frontend/`:

```bash
npm test -- --run --maxWorkers=2
npm run lint
npm run build
```

En este entorno Windows se ejecutaron las entradas CLI de Vitest, ESLint y
Vite con el runtime Node disponible, equivalentes a los scripts anteriores.
Se revisó `git diff --check` y el contenido de los archivos nuevos; no se
incorporaron claves ni configuraciones reales.

## Documentación y pendientes de cierre

### Ampliación aprobada durante la revisión (05/10/2026)

La persona responsable pidió incorporar filtros de propiedades, propietarios
e inquilinos **en esta misma rama**. Se añadieron búsqueda visible y sincronizada
en los listados de personas, panel responsive y recuperación de páginas fuera
de rango. No cambian estimaciones, dependencias ni migraciones. La última
validación de la rama obtuvo **429 passed / 41 skipped** en backend,
**191 passed** en frontend y **2 passed** en PostgreSQL local; lint, build y
revisión visual de los tres listados aprobados. Los resultados de la tabla
anterior corresponden al Home antes de esta ampliación.

Alcance, decisiones, pruebas, paginación y pendientes en
[`hu31_filtros_listados.md`](hu31_filtros_listados.md).

- README y seguimiento del Sprint 3 actualizados con este alcance.
- Se intentó registrar la decisión en **Decisiones técnicas (ADR)** de Notion;
  la operación falló con HTTP 403: el espacio agotó sus bloques gratuitos.
  **La publicación en Notion no está realizada.** Este documento conserva el
  contexto, alternativas y decisión para sincronizar cuando el espacio permita
  escribir, según el acuerdo de planificación del Sprint 3.
- HU y subtareas permanecen **En curso**. Se registraron las **2h** confirmadas
  por la persona responsable, sin modificar la estimación original del Sprint.
- Después del merge de HU13: actualizar la rama con `main`, conservar ambos
  cambios de navegación, conectar **Revisar casos** y verificar que el contador
  coincida con la cola y cambie después de una resolución manual.
- La persona responsable aprobó la revisión visual y autorizó commit/push.
  Queda abrir/revisar el PR; no dar HU31 por finalizada hasta completar su
  integración y revisión.
- No se probó la conexión del panel con el Supabase compartido: el SQL sí se
  ejecutó contra PostgreSQL real local. Una prueba externa requiere autorización.

### Registro de tiempo autorizado (05/10/2026)

El total de **2h** fue confirmado por la persona responsable. La distribución
es orientativa según el peso del trabajo realizado, no una medición automática
del tiempo por subtarea. Los worklogs se registran solo en las subtareas, sin
duplicar las dos horas en la HU padre.

| Subtarea | Actividad | Tiempo | Worklog |
|---|---|---|---|
| AARI-333 | Integración con sesión, rutas y destino administrativo. | 10 min | 10263 |
| AARI-334 | Pruebas, PostgreSQL local, revisión responsive y documentación. | 40 min | 10264 |
| AARI-335 | Home, estados, filtros, búsqueda sincronizada y paginación. | 35 min | 10265 |
| AARI-336 | Diseño responsive, navegación y ajustes visuales. | 15 min | 10266 |
| AARI-337 | Resumen privado y consultas filtradas con totales paginados. | 20 min | 10267 |
| **Total** | | **120 min / 2h** | |
