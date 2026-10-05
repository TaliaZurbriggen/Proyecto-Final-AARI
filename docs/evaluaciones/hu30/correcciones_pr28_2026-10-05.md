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
