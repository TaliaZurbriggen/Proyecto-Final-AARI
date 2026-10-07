# HU13 / AARI-147 — Correcciones de revisión del PR #29

## Alcance y estado

Propuesta aprobada por Talía el 07/10/2026. Rama
`codex/AARI-147-resolucion-escalados`, rebaseada desde `053236ac` sobre
`origin/main` `439ee3c3ec158ac389ebf0fdc8743f04cfa4ee47`, que ya incluye HU14
y HU30. Referencia local de respaldo: `backup/pr29-before-rebase-20261007`.
Commit recreado por el rebase: `de91ecf32ff2c917b61e7a03920fb97d54338d87`.
Talía autorizó el commit y la publicación de las correcciones el 07/10/2026,
después de la validación real en Supabase. Esta entrega actualiza el PR #29 para
nueva revisión de Tobías. No se fusionó el PR ni se cerraron tareas o registraron horas.

## Observaciones atendidas

1. **Límite de acceso a la cola.** `get()` y `photo()` comparten un predicado
   que exige estado actual Escalado/Clasificación pendiente, historial de
   ingreso a cualquiera de esos estados o decisión manual auditada. Reclamos
   nunca escalados devuelven `404` a administración y operación, incluso si
   tienen un UUID y una foto válidos. No se consulta Storage después del rechazo.
   Los casos históricos siguen consultables, pero no vuelven a ser resolubles.
   El listado conserva su filtro exclusivo de pendientes y su paginación.
2. **Destinatarios habilitados.** La migración 26 ya aplicada permanece idéntica.
   La incremental `20261007224000_hu13_destinatario_habilitado.sql` agrega
   `AND NOT primer_ingreso` a la función del aviso, conservando prioridad,
   idempotencia, `SECURITY INVOKER`, permisos y `search_path` vacío. Si el
   operador asignado aún no ingresó, se elige otro operador o administrador
   habilitado. Si ninguno puede acceder, no se genera correo sin destino.
   No se reenvían ni modifican alertas antiguas.
3. **Objetos e historial de migraciones.** El comprobador no retorna por la sola
   existencia de objetos. Contrasta registro de 26, objetos y corrección de
   función, también en modo de sólo lectura. Detecta ambas direcciones de deriva
   y registros duplicados; se detiene sin inventar entradas de historial.
   Aplicación nueva, actualización desde 26 y registro son transaccionales.
   Un fallo al registrar revierte el DDL; repetir una aplicación coherente no
   duplica registros ni tablas.

## Integración del rebase

Se resolvieron seis archivos: README, `backend/app/db/reclamos.py`,
`backend/app/main.py`, guía de migraciones y layouts de administración/operación.

- Se conservan routers de configuración, expensas, contratos y escalados,
  colocando `/reclamos/escalados` antes de rutas genéricas UUID.
- El guardado automático conserva el contexto contractual recibido de HU30;
  una decisión humana no borra el snapshot previo. Se mantienen los bloqueos,
  permisos, versión esperada, auditoría y protección contra reclasificación.
- Las expensas manuales producen sólo `expensa_reporte`, no además
  `responsable_inicial`. El reporte lleva origen operador/administrador y
  confianza nula. La derivación y su aviso al inquilino sólo ocurren después
  del resultado de entrega registrado; no se eliminan avisos previos de escalado.
- La cabecera compartida conserva ambos accesos, Casos escalados y Expensas,
  y el módulo activo correcto. No se muestran a inquilinos/propietarios.
  Se reutilizan componentes y estilos de la skill AARI Frontend; no hay rediseño
  ni cambio de paleta, dependencias o variables de producción.
- Se conservan HU30, sus evidencias congeladas, atributos LF/CRLF y recursos OCR.
  La selección de las dos migraciones `23_*` en las pruebas es por nombre
  completo, sin depender del orden de un glob.

## Validaciones ejecutadas

Desde `backend`, con dotenv deshabilitado, credenciales ficticias, workers y
banderas externas desactivados, y `AARI_TEST_POSTGRES_URL` hacia PostgreSQL 17
local exclusivo de QA:

```bash
python -m pytest -q --tb=short -o faulthandler_timeout=60
```

Resultado: **713 aprobadas, 37 omitidas, 0 fallidas**. En esta pasada local no
se habilitaron servicios/banderas externas; las omitidas no se presentan como
pruebas reales aprobadas de Supabase. La validación externa autorizada posterior
se registra por separado debajo. Se mantienen 19 advertencias
preexistentes de Starlette/httpx y del adaptador datetime SQLite, sin cambiar
dependencias ajenas al alcance.

La primera suite focalizada HU13 aprobó 68 pruebas; el backend completo incluye
además las dos regresiones de entrega simulada para operador y administrador.
Las nuevas pruebas PostgreSQL cubren rechazo HTTP/repositorio de detalles y
fotos de reclamos nunca escalados, pertenencia histórica, fallback, ausencia
de personal habilitado, drift de historial en ambas direcciones, upgrade de
26 sin cambios a su registro, idempotencia y rollback de la incremental.
También cubren snapshot contractual, expensa manual, aviso no duplicado y
auditoría. Las pruebas existentes de decisiones simultáneas siguen aprobadas.

Desde `frontend`:

```bash
npm test -- --run --maxWorkers=1
npm run lint
npm run build
```

Resultado: **151 pruebas aprobadas en 29 archivos**, lint/build correctos.
Se agregaron seis regresiones de navegación para roles y módulos activos.
Las APIs de las pruebas son dobles; no se inicia sesión con credenciales reales.

Preview del build en `127.0.0.1:5185` y script
`frontend/scripts/qa-escalados-navigation.mjs`, usando Playwright ya disponible
en el entorno (`AARI_BROWSER_MODULES`) y `AARI_PREVIEW_URL` local:

```bash
node scripts/qa-escalados-navigation.mjs
```

Resultado: **8 controles aprobados** (2 roles × 2 anchos, 390/1440 px × 2
bandejas), sin desborde horizontal de página, con módulo activo, ausencia de
búsqueda global duplicada y recorrido de teclado correcto. Cero errores de
JavaScript y cero llamadas externas reales. Evidencia local ignorada por Git:
`backend/artifacts/hu13-pr29-navigation/results.json` y ocho capturas PNG.
El preview se detuvo al terminar. Se comprobó que no quedaran bases
`aari_pr26_*` y se retiró únicamente el contenedor PostgreSQL ficticio creado
para esta revisión; se conservaron las capturas y los demás entornos locales.

`git diff --check`: correcto. La migración 26 no cambió respecto del respaldo.

## Validación Supabase autorizada — 07/10/2026

Talía autorizó expresamente aplicar la incremental y ejecutar el QA con datos
ficticios y rollback. Desde el backend de este worktree:

```bash
python scripts/check_escalados_postgres.py --env-file RUTA_ENV_LOCAL --mode check
python scripts/check_escalados_postgres.py --env-file RUTA_ENV_LOCAL --mode apply
python scripts/check_escalados_postgres.py --env-file RUTA_ENV_LOCAL --mode test
```

La ruta corresponde a un `.env` local y nunca se pega ni se publica su contenido.
La comprobación previa confirmó que la 26 estaba instalada coherentemente y
la corrección de destinatarios era lo único pendiente. `apply` aplicó sólo la
incremental, de forma transaccional. Una consulta de sólo lectura posterior
confirmó objetos y registros coherentes, sin duplicados:

- Base conservada: versión `20261005191504`, nombre `hu13_resolucion_escalados`.
- Incremental: versión `20261007224000`, nombre `hu13_destinatario_habilitado`.

Se verificaron auditoría, índices, trigger, filtro de primer ingreso, RLS y
permisos. **QA real HU13: 9 aprobadas, 0 fallidas en 111,98 segundos**, con una
advertencia preexistente de TestClient/httpx. Se recorrieron los tres tipos de
gasto para administración y operación, decisiones repetidas/desactualizadas,
cuentas desactivadas, auditoría, avisos idempotentes y el flujo HTTP. Las expensas
manuales usan `expensa_reporte`, coherente con HU14.

Cada prueba terminó con rollback y comprobó por sus propios IDs que no quedaran
personas, cuentas, inmuebles, reclamos ni relaciones ficticias. No se consumió
la secuencia normal de reclamos. Los workers permanecieron deshabilitados y
Gemini, SMTP y Storage se bloquearon con dobles: no hubo llamadas reales a esos
servicios ni envío de correos. No se modificaron reclamos o avisos preexistentes.
No repetir la 26 ni la incremental por hacer pull.

## Límites y siguiente paso

El formulario y los reportes siguen sujetos a la revisión funcional del equipo.

La revisión no instaló dependencias, no llamó a Gemini, no envió correos ni
modificó documentos de contratos. Notion no se actualizó: la decisión original
permanece documentada en `hu13_resolucion_escalados.md` por el límite de bloques
ya informado. No se cambia el alcance de producto acordado.

Antes de publicar, confirmar que la rama remota sigue en el head esperado y
actualizarla con `--force-with-lease` explícito, no force sin comprobación, porque
el rebase recreó su commit. La publicación fue autorizada; el merge requiere
una nueva indicación después de la revisión de Tobías.
