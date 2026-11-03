# HU20 — Comparar y seleccionar presupuestos

Fecha: 01/11/2026. Jira: AARI-220 y subtareas AARI-221–228.
Rama: `codex/AARI-220-seleccion-presupuestos`; base actualizada: main `879fa07`.
Estado: implementación validada localmente; publicación autorizada para revisión
de Talía. Pendiente validación compartida; sin cierre de HU/subtareas.

**Actualización 02/11/2026:** la migración HU20 fue aplicada y verificada con
autorización en Supabase durante la integración HU23. Cuatro recorridos HTTP
HU20→HU23 aprobaron con autenticación real de cuentas ficticias y rollback, sin
SMTP, Gemini ni Meta. Este resultado actualiza el pendiente compartido del
01/11, no modifica su evidencia histórica ni estados de Jira.
Ver [registro compartido HU23](hu23_coordinacion_visitas.md#supabase-y-autenticación-real--02112026).

## Alcance y decisiones

Se mantiene el alcance aprobado: propuestas estructuradas de HU19 con importe
positivo, ARS/USD y tipo exacto o mínimo. El responsable compara nombre,
especialidades, cobertura, importe y descripción. Se ordena por moneda/importe
ascendente, sin convertir monedas ni escoger al más barato automáticamente.
«Desde» expresa un piso, no precio final ni máximo autorizado. No se incorporó
la propuesta retirada de elegir sin presupuesto o negociar el precio mediante
un agente. Los mensajes de chat no confirman una elección.

Cada elección requiere revisión y confirmación explícita. El servidor determina
identidad, proveedor e importe: nunca los toma de datos monetarios del cliente.
Persiste la decisión y pasa a `Proveedor seleccionado`; HU23 coordinará la
visita. No se programa fecha, no se realiza pago y no se cambia HU21/AARI-345.

### Alternativa de proveedor propio e integración con HU18

Durante la preparación, HU18 no estaba en main. El usuario aprobó dejar la
opción visible sin escribir un estado intermedio hasta integrar su formulario.
El 01/11 se verificó PR #40 integrado en main `879fa07` y se actualizó HU20.

La opción ahora navega a la ruta `proveedor-externo` de HU18 cuando sus reglas
permiten registrar un contacto. Abrir el formulario no modifica el estado ni
cierra la ronda. Confirmar nombre/teléfono en HU18 realiza la derivación con su
propia auditoría, cancela la ronda y bloquea una selección posterior de HU20.
El caso inverso también queda bloqueado: no se registra contacto externo una
vez seleccionado un presupuesto. Se conserva HU17 como decisión histórica.

Se descartó cambiar a `Pendiente de datos de proveedor propio` desde HU20 porque
la elección original sigue siendo fidelizada y HU18 no acepta esa combinación.
No se modificó el repositorio de HU18 para introducir una segunda forma de
derivación. La ausencia de propuestas no fabrica presupuesto ni proveedor;
HU18 aplica sus propias reglas de etapa y vencimiento.

Por indicación del responsable, la documentación se mantiene versionada en el
repositorio de GitHub: este documento, README y guía de migraciones. El PR
resumirá decisiones, validaciones y pendientes cuando se autorice su publicación.
No se requiere documentación adicional en Notion.

## API y permisos

- `GET /reclamos/{id}/presupuestos`: contrato HU19 conservado, orden por moneda,
  monto y solicitud. No se exponen competidores al proveedor.
- `GET /reclamos/{id}/seleccion-presupuesto`: contexto, propuestas comparables,
  permisos vigentes, versión de reclamo, ronda y decisión persistida.
- `POST /reclamos/{id}/seleccion-presupuesto`: `request_id`, `ronda_id`,
  `expected_updated_at`, `modalidad=fidelizado`, `presupuesto_id`.

Sólo el responsable actual (inquilino ordinario o propietario autorizado)
confirma. Se revalidan cuenta activa, rol, primer ingreso, perfil y vínculo a la
propiedad. Administrador y operador asignado sólo consultan; proveedor no accede
a la comparación. Las respuestas exitosas usan `Cache-Control: no-store`.
Campos extra, IDs inválidos y fechas sin zona se rechazan. Un conflicto de
etapa/versión/petición se informa como 409, sin sobreescribir decisiones.

La consulta comparativa agrupa datos de proveedores en lote: no agrega tres
consultas por cada propuesta. Se preserva la distinción exacto/mínimo en todos
los resúmenes. La selección histórica conserva además el nombre del proveedor
en ese momento, aunque su perfil cambie luego.

## Atomicidad e idempotencia

Orden de bloqueo compatible con HU17/HU18: cuenta, perfil, propiedad, reclamo;
después ronda, presupuesto y cuenta del proveedor. La petición compara versión,
intento y huella del contexto HU19. El presupuesto debe pertenecer a la misma
ronda, reclamo y proveedor, con acceso vigente y cobertura/especialidad válida.
Se relee el presupuesto después de adquirir sus bloqueos.

Una transacción guarda proveedor/presupuesto/monto en reclamos, historial de
estado, snapshot auditado, cierre de recepción y aviso de salida. Un fallo
revierte todo. Una petición idéntica recupera la misma decisión sin duplicar
correo/historial. Reutilizar UUID con otros datos da conflicto. Dos elecciones
simultáneas tienen un único ganador. El frontend conserva UUID ante conexión
perdida o errores 5xx y bloquea doble confirmación.

`reclamo_selecciones_presupuesto` contiene elección, ronda, petición, versión,
usuario, nombre del responsable, proveedor/nombre, presupuesto, importe,
moneda/tipo, fecha y referencia a historial. Las FK compuestas evitan referencias
cruzadas entre reclamos. No hay rutas públicas para editar esta auditoría.

## Avisos privados

La solicitud propia del proveedor muestra que su presupuesto fue elegido,
incluso sin HU33. No enumera competidores ni sus precios. Si HU33 está habilitada,
se agrega un evento idempotente únicamente a los dos hilos individuales del
presupuesto elegido (proveedor y responsable), no a consultas técnicas ni a los
hilos de otros proveedores.

El correo se encola, no se envía dentro de la confirmación. El worker existente
revalida selección/estado, cuenta del proveedor y destinatario antes de SMTP;
un aviso obsoleto se cancela. Reintentos no repiten la elección. Un envío que
SMTP ya aceptó no puede retirarse; el control no promete recepción ni elimina
esa ventana externa. El cliente distingue elección guardada de correo recibido.

## Migración y entorno

`backend/migrations/20261029120000_hu20_seleccion_presupuesto.sql` es aditiva y
transaccional. Requiere HU17 y HU19 AARI; HU18 soporta la alternativa y HU33 el
chat opcional. Agrega clave única compuesta a presupuestos y la auditoría con
sus índices, RLS y permisos revocados a PUBLIC/anon/authenticated. No modifica
importes históricos, no agrega contactos reales ni aplica DDL al arrancar.

**No aplicada desde la entrega del 01/11; aplicada posteriormente con HU23 el
02/11/2026, con autorización y verificación.** Antes de habilitar la comparación
en una base, aplicar/verificar la migración con autorización expresa, respaldo
y ensayo con rollback. No ejecutar el SQL nuevamente si ya existe: revisar
historial/esquema primero. No se requiere reinstalar dependencias ni agregar
claves al `.env`. Se reutiliza `AARI_QUOTE_PORTAL_ENABLED`; no habilitarlo en un
entorno que no tenga el esquema HU20 al desplegar esta funcionalidad.
Mantener apagados workers generales salvo autorización específica.

## Validación reproducible sin servicios externos

Desde `backend/`, con el entorno Python del proyecto disponible:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:DATABASE_URL='sqlite:///:memory:'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests
```

Para integración, usar `AARI_TEST_POSTGRES_URL` exclusivamente con una instancia
local dedicada a pruebas. Los fixtures verifican host loopback y crean/eliminan
sólo bases `aari_pr26_<uuid>` por caso. No reutilizar la URL de Supabase.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_quote_selections_postgres.py tests/test_quote_portal_postgres.py tests/test_provider_choices_postgres.py tests/test_conversations_postgres.py tests/test_external_providers_postgres.py
```

Desde `frontend/`:

```powershell
npm run test -- --pool=threads --maxWorkers=1 --testTimeout=20000
npm run lint
npm run build
```

En esta ejecución se utilizó el Python 3.12 existente de un entorno de QA,
sin instalar paquetes. Se deshabilitó dotenv y no se cargaron credenciales SMTP,
Gemini o Meta. La entrega SMTP se probó mediante un sender simulado.
Evidencias detalladas locales en `backend/artifacts/hu20/` (ignoradas por Git).

La batería sin PostgreSQL terminó con **1199 aprobadas / 528 omitidas**;
las omitidas requieren integración local o ejecuciones opt-in, no acreditan
validación compartida. Los primeros intentos detectaron bloqueo del temporal
de Windows y un test que requiere ejecutarse desde `backend/`; la repetición
usó una carpeta temporal nueva dentro de artifacts y el directorio correcto.
Se conservaron las advertencias conocidas del adaptador datetime de SQLite.

Resultados finales adicionales:

- HU20 PostgreSQL: **36 aprobadas**, incluyendo flujo HTTP real contra la base
  local, ordinario/extraordinario, exacto/mínimo, versión, permisos, concurrencia,
  replay, rollback, RLS, snapshot, avisos privados, reintento SMTP simulado,
  cancelación de aviso obsoleto e integración con HU18.
- Regresiones PostgreSQL HU17/HU18/HU19/HU33: **155 aprobadas**. La corrida
  conjunta inicial tuvo 190 aprobadas y un fallo de fixture HU20: cambiaba sólo
  el correo del perfil y violaba la identidad HU32. Se corrigió actualizando
  perfil y cuenta juntos; la repetición completa de los 36 casos HU20 pasó.
  No se atribuye a esa corrida inicial un resultado verde que no tuvo.
- Frontend: **467 aprobadas en 44 archivos** usando pool de hilos. La ejecución
  inicial con procesos quedó sin progreso y se detuvo; no se contabiliza como
  aprobada. Incluye 12 casos nuevos de comparación y el aviso de selección en
  el portal del proveedor, además de las regresiones de HU18.
- `npm run lint` y `npm run build`: correctos. Se conserva el aviso conocido de
  bundle superior a 500 kB; no se cambió la arquitectura de carga en esta HU.
- `git diff --check`: correcto. Revisión de patrones de secretos y espacios
  finales en los 12 archivos nuevos: sin coincidencias. El cambio ajeno de
  `docs/hu11_historial_reclamos.md` conserva exactamente su blob previo al rebase.

Los procesos de QA se detuvieron al finalizar: cero bases `aari_pr26_*`
remanentes, PostgreSQL local apagado y vista temporal retirada. Las capturas
`desktop.jpg` y `mobile.jpg` quedan como evidencia ignorada por Git.

QA visual aislado con los componentes reales y API simulada: comparación,
confirmación, selección guardada, vacío y navegación a HU18; escritorio/móvil,
teclado y foco. La revisión móvil detectó y corrigió el botón con nombre largo.
Este recorrido no equivale a un login real ni valida instalación compartida.

## Correcciones de revisión del PR #41 — 01/11/2026

Se atendieron los dos hallazgos de presentación del
[comentario de Talía](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/41#issuecomment-6567297227),
con alcance limitado al componente de comparación y sus pruebas; sin cambios de
API, backend, base, dependencias ni estilos compartidos.

- La confirmación obtenida del POST se renderiza fuera del bloque dependiente
  del GET. Continúa visible mientras se actualiza y si falla la consulta. Se
  distingue una advertencia de actualización de un error al guardar; el botón
  «Reintentar actualización» sólo repite el GET, nunca la selección.
- El resumen del reclamo muestra exclusivamente `data.estado`, su estado
  vigente consultado. El snapshot se conserva en el detalle con la etiqueta
  «Estado al confirmar la selección». Si no se pudo actualizar el reclamo, no
  se presenta ese valor histórico como un estado actual verificado.
- Se conserva el foco en la confirmación aun durante la recarga y se reutilizan
  `AlertMessage`, `LoadingState`, `Button`, `StatusBadge` y layouts existentes.

Cinco regresiones nuevas reprodujeron los fallos antes de modificar el
componente; tras la corrección pasan las **17 pruebas del componente**. Incluyen
inquilino/propietario, POST exitoso + GET fallido, reintento sólo de lectura,
estado actual «Resuelto» con selección histórica y consulta aún pendiente.
Comando: `npm run test -- --pool=threads --maxWorkers=1 --testTimeout=20000
src/features/reclamos/pages/BudgetComparisonPage.test.jsx`.

Regresión completa del frontend: **472 aprobadas en 44 archivos**, sin fallos,
con `npm run test -- --pool=threads --maxWorkers=1 --testTimeout=20000`.
`npm run lint`, `npm run build` y `git diff --check` correctos; se conserva el
aviso conocido de bundle >500 kB. No se repitió el backend: esta corrección no
modifica su código ni atribuye a esta ejecución nuevas pruebas de PostgreSQL.

QA aislado escritorio (1440 px), móvil (390 px) y teclado con API simulada:
confirmación visible tras 503, reintento sin incrementar el contador de POST y
consulta de selección histórica con estado vigente «Resuelto». Sin desbordes
horizontales en móvil. Evidencias ignoradas en `backend/artifacts/hu20/`:
`review-red.json`, `review-green.json`, `review-frontend-all.json`, `review-refresh-error-desktop.jpg`,
`review-refresh-error-mobile.jpg` y `review-current-state-desktop.jpg`. Vista
temporal y servidor de QA retirados al finalizar; no se usó Supabase ni SMTP.

## Pendientes registrados al 01/11/2026

- Aplicación/verificación autorizada del esquema HU20 en Supabase y recorrido
  autenticado compartido: cubiertos el 02/11 desde HU23, sin envío real.
- Revisión de Talía en el PR; commit/push/publicación autorizados por el usuario.
- Tiempo real por confirmar con el usuario; no se registró tiempo nuevo ni se
  cerraron HU/subtareas en Jira durante esta implementación.
