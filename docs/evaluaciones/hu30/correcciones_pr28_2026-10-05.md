# HU30 — correcciones del PR #28

Fecha: 05/10/2026. Rama: `feat/AARI-319-extraccion-clausulas`.
Talía autorizó implementar las tres observaciones de revisión y subirlas al PR.
No se autorizaron nuevas llamadas externas, cambios de estimaciones ni cierre.

## Integración con main

Se incorporó `origin/main` (`053a712`) mediante merge, sin reescribir el historial.
Los cinco conflictos se resolvieron conservando el contexto contractual de HU30
y las protecciones de AARI-135:

- Validación de estado/clasificación antes de ejecutar el grafo y nuevamente
  dentro de la transacción, bajo bloqueo del reclamo.
- Persistencia atómica del resultado, snapshot contractual, actor responsable
  y bandeja de notificaciones; seguimiento y vencimientos idempotentes.
- Respuesta pública mediante `PersistedClassification`, sin perder la
  notificación que el endpoint intenta entregar después de confirmar la DB.

No se eliminaron casos de prueba de ninguna rama. La guía conserva ambas
migraciones con prefijo `23_`, identificadas por su nombre completo; no se
renombraron migraciones ya aplicadas ni se ejecutaron en Supabase. La instalación
aislada de prueba carga explícitamente ambos archivos, además de 20, 24 y 25.

## Vigencia del contexto contractual

La fecha de creación del reclamo se convierte explícitamente mediante
`AT TIME ZONE 'America/Argentina/Buenos_Aires'` antes de compararla con el inicio,
el fin pactado o la finalización anticipada. No depende de `TimeZone` del servidor.
Se mantiene el último día incluido en la vigencia; no cambia la regla del producto.

La regresión recorre cinco instantes de inicio/fin, incluyendo el reclamo del
30/06 a las 22:00 de Argentina (`01/07 01:00 UTC`) y el cambio de día a medianoche.
Se repite con sesiones UTC, Tokio y Argentina y con fin pactado/finalización
anticipada: seis escenarios parametrizados, treinta comprobaciones de fecha.

## Reserva de trabajos y Gemini

El worker reserva **un trabajo justo antes de procesarlo**, no tres que esperen
en serie con la misma caducidad. Mantiene una renovación cada 60 segundos durante
OCR/HTTP, con reserva de 180 segundos. Sólo el UUID de ejecución actual, en estado
procesando y con reserva aún vigente, puede renovarla; una reserva expirada no
puede revivir. La comprobación se repite antes de enviar texto al modelo y antes
de guardar. Ante pérdida/error de renovación, se detiene ese worker sin completar
ni fallar el intento que pudiera haber recuperado otro.

Se eligió combinar adquisición individual y renovación: la primera elimina las
reservas de trabajos en espera; la segunda protege el trabajo activo si la
descarga/OCR/análisis tarda más de lo esperado. No se agregó una dependencia ni
se cambió el prompt o la política de una petición HTTP por invocación.

La prueba con dos workers y tres trabajos retiene la primera respuesta simulada,
acerca su vencimiento y verifica una renovación real en PostgreSQL. El segundo
worker procesa sólo los otros dos: **tres invocaciones y tres intentos**, no seis.
Otros casos verifican UUID incorrecto, reserva vencida, recuperación con nuevo
UUID y pérdida de reserva antes de descarga, modelo o persistencia.

Esto evita la duplicación por reservas de trabajos en espera o caducidad de un
worker activo que puede renovar. **No ofrece exactamente una llamada global
ante una caída real/partición**: una petición ya enviada no puede cancelarse ni
deduplicarse en el proveedor con la reserva de DB. Se conserva la recuperación
durable y la auditoría existentes; ninguna prueba consume una API externa.

## Validación final

| Validación | Resultado |
|---|---|
| Backend sin DB externa ni PostgreSQL optativo | `pytest -q`: 553 aprobadas, 49 omitidas, 2 advertencias conocidas |
| Backend integrado con PostgreSQL local | `pytest -q`: 574 aprobadas, 28 omitidas, mismas 2 advertencias |
| Regresiones locales HU30 + AARI-135 | 21 aprobadas, incluidas en las 574 anteriores |
| Prueba histórica de migraciones/revisión/RLS | `test_contract_clauses_postgres.py`: 1 aprobada por separado, rollback |
| Frontend | `npm test -- --run`: 112 aprobadas; `npm run lint` y `npm run build`: correctos |

No sumar dos veces las regresiones locales que ya integran la suite completa.
Las omisiones corresponden a pruebas optativas/externas, no a pruebas aprobadas.
La validación se hizo en PostgreSQL 17 local descartable, con datos sintéticos:
no se accedió a Supabase, SMTP ni Gemini y no se enviaron documentos privados.

Para reproducir las regresiones, configurar `DATABASE_URL=sqlite://` y
`AARI_TEST_POSTGRES_URL` hacia un PostgreSQL **local dedicado** con los roles
sin login `anon` y `authenticated`. Desde `backend/`:

```text
python -m pytest -q tests/test_contract_worker_leases.py
python -m pytest -q tests/test_contract_clauses_local_postgres.py tests/test_responsible_actor_postgres.py
python -m pytest -q
```

El fixture valida que el host sea local, crea una base `aari_pr26_<uuid>` por
escenario y la elimina al terminar. No usar una URL de Supabase en esa variable.
La prueba histórica separada usa `RUN_CLAUSES_POSTGRES_TESTS=1` y `DATABASE_URL`
local, crea un esquema aislado y lo revierte. Los ensayos iniciales de esta
corrección detectaron dos errores del fixture nuevo (importación y ausencia de
la página sintética); se corrigieron antes de obtener los resultados finales.

Pendiente: revisión de Tobías y merge del PR. Se mantienen la revisión humana
obligatoria y las limitaciones semánticas publicadas; estas regresiones no
revalúan ni mejoran artificialmente la precisión de Gemini.

## Segunda revisión — HU11, checkout Windows y recursos OCR

Talía aprobó implementar esta ronda sobre la misma rama. Tras validar los
resultados, autorizó el commit/push y comentarios de respuesta en GitHub y Jira.
No autorizó merge del PR, horas adicionales de Jira ni llamadas externas.

### Actualización de main

Se preparó la integración de `origin/main` en `80afb67`, que incorpora el PR #27
de HU11/AARI-125. El único conflicto fue `README.md`: se conservaron el historial
por propiedad de HU11, HU12/AARI-135 finalizada y el alcance asistido de HU30.
`backend/app/main.py` se combinó automáticamente. Se mantienen la protección
contra reclasificación, la bandeja de notificaciones y el contexto contractual.
El merge se incorpora en el commit de entrega autorizado, sin reescribir historial.

### Hashes sin depender de CRLF/LF

Se eligió `.gitattributes`, no normalizar silenciosamente `file_sha256()`:

- Las entradas textuales congeladas se materializan con `text eol=lf`, incluso
  si `core.autocrlf=true`. La cobertura incluye los ejecutores de diagnóstico
  que registran su propio hash fuera de `prompt_freeze`.
- La evidencia de `docs/evaluaciones/hu30/` conserva los bytes del blob con
  `-text`, incluyendo archivos históricos que ya usan CRLF. Sólo el archivo
  de controles congelados tiene una excepción explícita `text eol=lf`.
- Los PDF conservan bytes originales con `-text`; su SHA sigue siendo binario.
- No se recalcularon manifiestos, no se normalizaron resultados históricos y
  no se modificó `contract_text_extraction.py` ni la función de hashing.

Las regresiones crean repositorios Git locales con `autocrlf=true/false`,
parten de textos CRLF y comprueban el checkout LF, el hash histórico del
prompt/OCR/diagnóstico, la evidencia mixta sin conversión y el PDF intacto.
También confirman que un cambio real de contenido sigue siendo rechazado.

La primera ejecución Windows encontró otro hash de diagnóstico, no listado
en los manifiestos. Se amplió la política antes de repetir la suite completa;
no se modificó el script ni el registro para disimular esa diferencia.

### OCR del flujo actual

`contract_ocr.py` agrega `ManagedTesseractOcrEngine`. El worker y la evaluación
asistida actual lo usan explícitamente; los ejecutores históricos conservan el
adaptador congelado para no alterar las evaluaciones previas.

El motor copia la imagen PIL antes de cerrar la imagen prestada, el bitmap,
la página y el documento PDFium. Tesseract recibe la copia independiente, que
también se cierra al finalizar. `ExitStack` garantiza los cierres en orden
inverso incluso si falla una etapa o algún cierre, sin depender del GC.
Se mantienen resolución, idioma y mensajes seguros; no cambia el prompt.

Las pruebas cubren éxito, errores al abrir documento/página, renderizar,
obtener/copiar PIL y ejecutar Tesseract, además de un fallo de cierre. Otra
prueba renderiza un PDF sintético con PDFium real y verifica que la copia
permanece legible tras cerrar los recursos nativos, con Tesseract simulado.
El ejecutor asistido aislado implementa la renovación de su reserva en memoria;
una prueba con modelo simulado verifica que no se detiene antes del análisis.

### Validación de esta ronda

Se materializó desde cero un checkout independiente del árbol preparado de Git,
con `core.autocrlf=true`, sin crear un commit ni copiar `.env`. El árbol de código
validado es `c918ff0fb394ffc826016a36522afa22cba74964`; las actualizaciones de esta
documentación son posteriores. `git diff --quiet` contra su índice pasó.
Se reutilizaron el entorno Python y las dependencias frontend ya instaladas;
no se afirma haber instalado dependencias desde cero. `pypdfium2` está declarado
en `backend/requirements.txt` y disponible en el entorno utilizado.

| Validación en checkout Windows | Resultado |
|---|---|
| Backend completo, sin servicios externos | `python -m pytest -q`: **588 aprobadas, 50 omitidas, 19 advertencias** |
| Regresiones nuevas de OCR/EOL | **15 aprobadas**, incluidas en las 588 |
| Frontend completo, un worker | `npm test -- --run --maxWorkers=1`: **122 aprobadas** |
| Prueba preexistente de operadores aislada | **14 aprobadas**, incluidas en las 122 |
| Frontend lint/build | `npm run lint` y `npm run build`: **aprobados** |
| Formato y revisión de secretos | `git diff --check` / `git diff --cached --check`: sin errores; ningún patrón de clave real detectado en líneas agregadas |

En una ejecución paralela frontend hubo un fallo intermitente de foco en
`Operadores.test.jsx`: el mensaje de error ya estaba renderizado pero el efecto
de foco todavía no se había comprobado. Pasó aislada y la suite completa pasó
con un worker. No se modificó ni omitió esa prueba; conviene estabilizar su
espera asíncrona en una tarea separada. Otra ejecución completa previa en la
rama también aprobó las 122. No se presenta el reintento como una corrección
de ese módulo.

Las advertencias son de compatibilidad de Starlette/httpx y del adaptador de
fecha de SQLite/Python, incluida su repetición en los tests nuevos de HU11.
Las 50 omisiones corresponden a integraciones optativas/externas: en esta ronda
no se ejecutó PostgreSQL ni el OCR real con el idioma español. La prueba de
liberación usa PDFium real y Tesseract simulado; no es una nueva medición de la
calidad de lectura o de la precisión semántica. No se accedió a Gemini, Supabase
ni SMTP, no se transmitieron contratos y no se ejecutó ninguna migración.

La guía de migraciones conserva los dos archivos `23_*` aplicados y detalla
el orden por nombre completo; para la siguiente se debe acordar un prefijo
único, actualmente `26_`. Entrega autorizada en la misma rama del PR #28;
pendiente nueva revisión de Tobías antes del merge. La HU permanece en curso.
