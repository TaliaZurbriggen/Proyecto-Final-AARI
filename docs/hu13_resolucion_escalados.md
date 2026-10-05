# HU13 / AARI-147 — Resolución humana de casos escalados

## Estado y alcance

Implementación aprobada el 05/10/2026 y realizada en la rama local
`codex/AARI-147-resolucion-escalados`, creada desde `origin/main` `80afb67`.
La HU y las nueve subtareas AARI-148 a AARI-156 están **En curso**, verificado
en Jira. No se modificaron las estimaciones. El 05/10/2026 se registraron
**1 h 10 min** de trabajo real informado y autorizado por Talía, distribuidos
aproximadamente según el esfuerzo de cada actividad, sin duplicarlos en la HU:

| Subtarea | Actividad | Tiempo | Worklog |
| --- | --- | --- | --- |
| AARI-148 | Cola, consulta, búsqueda y paginación | 5 min | 10255 |
| AARI-149 | Columnas y presentación del listado | 3 min | 10256 |
| AARI-150 | Detalle y formulario de clasificación | 10 min | 10257 |
| AARI-151 | Validaciones y bloqueo de confirmación | 2 min | 10258 |
| AARI-152 | Endpoint, permisos, conflictos y transacción | 10 min | 10259 |
| AARI-153 | Continuidad de LangGraph sin LLM | 5 min | 10260 |
| AARI-154 | Auditoría, migración y seguridad | 10 min | 10261 |
| AARI-155 | Aviso de entrada e idempotencia | 5 min | 10262 |
| AARI-156 | Pruebas, revisión y documentación | 20 min | 10254 |

Jira confirmó **4200 segundos acumulados** en AARI-147 y ningún worklog directo
en la HU padre. La HU y sus subtareas siguen En curso.
La publicación mediante commit y push fue autorizada el 05/10/2026. Talía
creará el PR para revisión de Tobías. La historia no se marca como terminada
ni se fusiona a `main` en esta entrega.

La inmobiliaria puede revisar y clasificar los reclamos `Escalado` o
`Clasificación pendiente` sin tipo de gasto ni solicitud de responsable.
Quedan fuera de esta cola los escalados posteriores de coordinación que ya
tienen responsable: HU13 no debe reemplazar una gestión iniciada.

## Interfaz y permisos

- Administración: `/escalados` y `/escalados/:reclamoId`.
- Operación: `/operador/escalados` y `/operador/escalados/:reclamoId`.
- Cola compartida, ordenada por ingreso ascendente e ID para desempatar;
  búsqueda literal por número, descripción o dirección y páginas de 20 casos.
- Columnas: número/estado, descripción/propiedad, ingreso, escalado y motivo.
  Si el caso nunca pasó por Escalado se indica que no hay escalado previo.
- Detalle: descripción completa, inmueble, inquilino, urgencia, fundamento,
  confianza disponible, fotos privadas, historial y decisiones humanas.
- Sin opción preseleccionada; fundamento obligatorio de 10 a 1000 caracteres
  luego de quitar espacios extremos. Confirmar permanece deshabilitado si falta
  alguno de esos datos y mientras se guarda. Se muestra el responsable antes de
  confirmar. Ante un conflicto se exige actualizar y volver a revisar.
- Un error no borra el fundamento escrito y una búsqueda fallida no conserva
  resultados de otros filtros. Las respuestas tardías no pisan consultas nuevas.
- Fotos obtenidas mediante FastAPI con autorización de personal, sin URL pública
  ni credenciales en el navegador; respuesta `private, no-store` y `nosniff`.
  Una falla de vista previa ofrece abrir nuevamente la foto.
- Se reutilizan componentes, tokens y la skill visual AARI. No se añade una
  navegación lateral ni otra paleta. Revisión de escritorio, tablet y celular.

Inquilinos y propietarios no acceden a esta cola ni pueden clasificar. Se
conserva la autenticación existente, incluida la comprobación de cuenta activa
y cambio obligatorio de contraseña inicial. La identidad de la decisión nunca
se recibe del formulario; proviene de la sesión del backend.

## Continuidad del flujo sin LLM

```text
Caso pendiente → selección y fundamento humanos
              → determinar_actor_responsable (LangGraph, sin clasificador)
              → guardar decisión + auditoría + transición + outbox
              → Pendiente de respuesta del responsable (HU12)
```

Mapeo: ordinario → inquilino; extraordinario → propietario; expensa →
inmobiliaria. Las tres decisiones continúan con el contrato actual de HU12.
La derivación específica de expensas corresponde a HU14. No se hacen llamadas
a Gemini y no se inventa una confianza del 100 %: la confianza manual es nula.

**Resolver el escalado significa decidir la clasificación, no cerrar el
reclamo ni declarar resuelta la reparación.** La interfaz lo aclara antes y
después del guardado. Clasificar tampoco elimina un riesgo de seguridad.

## Persistencia, auditoría y concurrencia

El repositorio reutiliza la persistencia de HU12 sin modificar su contrato
automático. El recorrido manual revalida y bloquea primero la cuenta y luego
el reclamo; comprueba rol activo, estado pendiente, ausencia de responsable y
la versión `updated_at` recibida. La versión conserva zona horaria y
microsegundos, sin convertirla a una fecha de JavaScript que pierda precisión.

Una transacción guarda:

1. Clasificación y fundamento, origen `operador` o `administrador`, fecha y
   confianza nula.
2. Transición con usuario real en el historial existente.
3. Auditoría con ID y nombre de la persona, rol, fecha, tipo de gasto y motivo.
4. Snapshot explícito del estado y resultado anteriores: tipo, confianza,
   fundamento, motivo de escalado, origen, clasificación y última actualización.
5. Solicitud del responsable y notificación idempotente de HU12.

Para administradores históricos sin nombre completo se usa su email como
identificación registrada, sin añadir un nuevo requisito de perfil a HU13.
La pantalla puede consultar el resultado original aun después de resolver.

Una decisión repetida, simultánea o desactualizada devuelve `409` sin alterar
lo guardado. Una cuenta desactivada se rechaza también dentro de la transacción.
La protección contra reclasificación automática de HU12 permanece activa.
Un fallo intermedio revierte clasificación, historial, auditoría y solicitud.
El correo se entrega después del commit mediante la bandeja existente:
los errores de SMTP no deben deshacer una decisión válida.

## Avisos al entrar a la cola

La migración 26 agrega un trigger al historial. Encola un aviso por entrada a
`Escalado` o `Clasificación pendiente` sin clasificación/responsable. Una
transición entre esos dos estados no es otra entrada y no repite el aviso.
La clave de idempotencia incorpora reclamo y evento de entrada.

Se mantiene la política de HU12: operador asignado si está activo, luego otro
operador activo y finalmente administrador activo, con orden determinista.
No se cambia la asignación ni se envía a todas las cuentas. Si no hay personal
activo no se inventa un destinatario: el caso permanece consultable en la cola
y no se crea un correo sin destino. No hay backfill de avisos históricos.
Se reutilizan outbox, worker y reintentos; no se envía correo desde PostgreSQL.

## Componentes principales

- `backend/app/api/escalados.py`: listado, detalle, foto privada y resolución.
- `backend/app/schemas/escalados.py`: contratos de entrada y salida.
- `backend/app/db/escalados.py`: consulta y evidencia del caso.
- `backend/app/db/reclamos.py`: guardado común y transacción manual.
- `backend/app/services/escalated_claims_service.py`: validaciones y grafo manual.
- `backend/app/agents/classification/graph.py`: entrada sin clasificador LLM.
- `backend/app/services/claim_storage.py`: descarga privada de fotos.
- `backend/migrations/26_resolucion_escalados.sql`: auditoría, índices y avisos.
- `backend/scripts/check_escalados_postgres.py`: verificación, aplicación
  autorizada y QA sintético de Supabase, sin imprimir credenciales.
- `frontend/src/features/reclamos/`: API, validación, listado y detalle manuales.
- `frontend/src/App.jsx` y layouts: rutas protegidas y acceso en navegación.

API: `GET /reclamos/escalados`, `GET /reclamos/escalados/{id}`,
`GET /reclamos/escalados/{id}/fotos/{foto_id}` y
`POST /reclamos/{id}/resolver-escalado`.
El POST recibe únicamente `tipo_gasto`, `fundamento` y `expected_updated_at`;
rechaza campos adicionales, sesiones ausentes y roles sin permiso.

## Migración y dependencias

La 26 es aditiva: tabla de auditoría con RLS habilitado y permisos revocados
a `anon`/`authenticated`, índices y función/trigger con `search_path` vacío.
No cambia migraciones históricas ni datos existentes. Requiere las de HU10/HU12
hasta `23_notificaciones_actor_responsable.sql`.

Los números 24/25 están reservados por HU30. Al integrarla habrá dos archivos
con prefijo 23; hay que respetar nombres completos e historial del entorno,
sin renumerar scripts ya aplicados. HU13 no depende de tablas contractuales.
Al actualizar esta rama con HU30 se deben conservar el contexto contractual y
las protecciones de HU12 junto con el nuevo camino manual.

**Aplicada con autorización en Supabase AARI de desarrollo el 05/10/2026
(Argentina)**, registro `20261005191504_hu13_resolucion_escalados`. Se comprobaron
los objetos y sus permisos después del commit. No se modificaron reclamos,
personas ni avisos existentes; no hay backfill. El script registra la migración
y su DDL en la misma transacción, con bloqueo para evitar aplicaciones
simultáneas. Se probó localmente que una segunda aplicación no repite el cambio
y que un fallo al registrar el historial revierte también el DDL.

Las pruebas locales usan bases nuevas `aari_pr26_<uuid>`, eliminadas después de
cada prueba. No se necesitan nuevas librerías ni variables de producción.

## Pruebas y resultados — 05/10/2026

Desde `backend`, con el entorno virtual existente y sin `.env` real:

```powershell
$env:DATABASE_URL='sqlite://'
$env:AARI_TEST_POSTGRES_URL='postgresql://postgres@127.0.0.1:55447/postgres'
../../../backend/venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
```

Resultado: **406 aprobadas, 35 omitidas**, 19 advertencias preexistentes
(adaptador datetime SQLite y deprecación TestClient/httpx). Las omitidas
requieren servicios externos o condiciones opt-in que no se habilitaron;
no son validaciones ejecutadas. La suite específica HU13:

```powershell
../../../backend/venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_escalados.py tests/test_escalados_postgres.py
```

Resultado: **51 aprobadas** (35 HTTP/grafo y 16 PostgreSQL local): permisos,
ausencia de sesión, validación de
campos/longitudes, grafo sin Gemini, fotos privadas, auditoría original,
los tres tipos de gasto, administrador y operador, decisión desactualizada,
dos personas simultáneas, competencia automática/manual, cuenta desactivada,
rollback con fallo inyectado, RLS, búsqueda/paginación y política de avisos.
Las dos nuevas pruebas del aplicador verifican que no repita la migración y
que un error al guardar el historial revierta todo el cambio de esquema.

### Supabase real, con autorización y rollback

Desde este worktree, usando la configuración privada existente del proyecto
sin copiarla ni imprimirla:

```powershell
../../../backend/venv/Scripts/python.exe scripts/check_escalados_postgres.py --env-file ../../../backend/.env --mode apply
../../../backend/venv/Scripts/python.exe scripts/check_escalados_postgres.py --env-file ../../../backend/.env --mode check
../../../backend/venv/Scripts/python.exe scripts/check_escalados_postgres.py --env-file ../../../backend/.env --mode test
```

Resultado final: **9 aprobadas**, una advertencia preexistente de TestClient.
Se recorrieron los tres tipos de gasto con operador y administrador, grafo real
sin clasificador, continuidad de HU12, auditoría original, usuario del historial,
una sola solicitud/notificación inicial, repetición rechazada, versión obsoleta,
cuenta desactivada, aviso sin duplicación entre estados de cola y flujo HTTP.
La verificación del esquema confirmó RLS, revocación de permisos públicos,
ausencia de políticas directas, función invoker con `search_path` vacío y trigger
activo.

Cada prueba creó sus propias personas, cuentas, inmueble y reclamo sintéticos,
dentro de una transacción externa con savepoints. Al terminar hizo rollback y
comprobó por sus IDs que no quedaran datos ni relaciones. Los números de reclamo
se asignaron explícitamente: **no se consumió la secuencia normal**. No se
modificaron reclamos existentes. El worker estuvo deshabilitado y los puertos de
Gemini, SMTP y Storage bloqueados por dobles; las notificaciones nunca quedaron
confirmadas para que otro worker las enviara. No hubo solicitudes a Gemini,
SMTP ni Storage reales.

En la primera pasada hubo tres fallos en la aserción que asumía que el evento
manual era siempre el último del historial. `now()` de PostgreSQL es constante
en la transacción externa de QA: distintas transiciones pueden tener la misma
hora y el desempate por UUID no representa su cronología. Se corrigió **la prueba**
para identificar la transición a responsable y comprobar su rol e ID de usuario,
sin relajar las verificaciones de auditoría. La segunda pasada aprobó las nueve.

### Frontend y revisión funcional local

Desde `frontend`:

```powershell
npm test -- --maxWorkers=1
npm run lint
npm run build
```

Resultado final: **121 pruebas aprobadas** en 26 archivos. La suite HU13 tiene
**11 pruebas aprobadas**, incluyendo decisión
sin preselección, fundamento, doble clic, versión exacta, conflictos,
preservación de texto, consulta tardía y foto no disponible. **Lint y build
aprobados**. No hay errores de formato en `git diff --check`.

Revisión funcional en navegador: frontend local → API real → PostgreSQL
local con datos ficticios, identidad sintética aislada y remitente simulado.
Se abrió la cola, se verificó el botón inicialmente deshabilitado, se seleccionó
extraordinario, se completó el fundamento y se confirmó. El detalle mostró
`Pendiente de respuesta del responsable`, origen humano y resultado original
conservado; el formulario dejó de estar disponible. También se recorrió la
decisión ordinaria desde Administración y quedó registrada con ese rol.
No hubo Gemini ni SMTP real. Se verificaron listado y detalle a 1536 px,
768 px y 390 px, con ancho del documento no mayor que el viewport. La
navegación horizontal interna en móviles es la del componente compartido;
no produce scroll horizontal de toda la página.
El harness de prueba queda ignorado en `backend/artifacts/`; no cambia la
autenticación de la aplicación ni debe usarse con datos/entornos reales.
La tipografía Inter se comprobó cargada; los servidores de preview y el
contenedor exclusivo de QA se detuvieron al finalizar. Se eliminaron las
tres bases ficticias que quedaron de la revisión visual, conservando la
captura local `backend/artifacts/hu13-decision-manual.jpg`.

## Decisión técnica para Notion — publicación pendiente

Se intentó agregar ADR-015 a la página existente de decisiones. Notion aceptó
el trabajo asíncrono, pero luego lo rechazó con `403 / block_limit_reached`:
el espacio agotó sus bloques gratuitos. **No quedó actualizado.** No se
eliminaron contenidos ni se cambió el plan para sortear esa limitación.

Contexto: una decisión humana debe resolver la incertidumbre sin perder
trazabilidad ni duplicar la gestión del responsable. Se eligió una cola
compartida, un recorrido de LangGraph sin LLM y un guardado transaccional con
auditoría. Se descartó volver a consultar Gemini, inventar confianza del 100 %
y crear otro sistema de asignación. Los motivos son preservar la decisión
humana, conservar evidencia, evitar cuota innecesaria y mantener el alcance de
HU13. Esta sección conserva la decisión aprobada hasta poder publicarla en Notion.

## Pendientes antes de integrar/cerrar

1. Revisión funcional del equipo en el entorno real; fotos reales/Storage
   y SMTP quedan fuera de las validaciones efectuadas.
2. Revisar e integrar cambios nuevos de `main`, especialmente HU30 si se
   mergea antes; conservar contrato de HU12 y contexto contractual.
3. Crear y revisar el PR (publicación de la rama autorizada el 05/10/2026).
   Mantener HU/subtareas En curso hasta el cierre acordado; registrar tiempo
   real solo cuando se indique.
4. Publicar esta decisión y la evidencia en Notion cuando el espacio permita
   nuevos bloques, sin afirmar que ya están sincronizados.
