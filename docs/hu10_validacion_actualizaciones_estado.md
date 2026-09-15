# HU10 — Validación de actualizaciones de estado

Fecha de validación: **14/09/2026**

Historia: **AARI-116**

QA del flujo: **AARI-124**

## Alcance validado

- listado y detalle exclusivos del inquilino autenticado;
- actualización automática cada 30 segundos sin solicitudes superpuestas;
- conservación de la última información visible ante errores temporales;
- historial cronológico de estados y estado actual;
- una notificación durable por cada transición real;
- tres intentos, recuperación de reservas vencidas y protección por número de
  intento ante workers concurrentes;
- convivencia de la migración 21 con la migración 20 de contratos.
- compatibilidad de la alerta histórica de tres cancelaciones con los campos
  obligatorios y la cola de entrega incorporados por la migración 21.

## QA transaccional en Supabase

Se ejecutó la prueba optativa:

```powershell
$env:RUN_SUPABASE_INTEGRATION='1'
.\.venv\python.exe -m pytest -q tests/test_claim_status_supabase_integration.py
```

Resultado: **1 prueba aprobada**. La prueba tomó un reclamo apto con
`FOR UPDATE ... SKIP LOCKED`, recorrió los **20 estados declarados** y verificó
en cada paso:

- exactamente una fila nueva de historial;
- estado anterior, estado nuevo y origen correctos;
- exactamente una notificación para el inquilino;
- estado de entrega `pendiente` y canal `email`.

Todo el recorrido se realizó dentro de una transacción que finalizó con
`ROLLBACK`. No se persistieron estados, historiales ni notificaciones de prueba,
y el worker no pudo observar las filas sin confirmar. No se invocó SMTP.

## Validaciones automatizadas

```powershell
# backend
.\.venv\python.exe -m pytest -q

# frontend
npm test
npm run lint
npm run build
```

Resultados locales después de incorporar la corrección:

- backend: **298 aprobadas, 21 omitidas**;
- frontend: **100 aprobadas**;
- ESLint: aprobado;
- build de Vite: aprobado;
- pruebas focalizadas de seguimiento: **5 aprobadas**;
- pruebas focalizadas de notificación/migración/API: **17 aprobadas**.
- pruebas focalizadas de migración y regresión de cancelaciones:
  **9 aprobadas, 2 omitidas**; las omitidas requieren Supabase autorizado.

La prueba de SMTP real queda fuera de este QA: las pruebas automatizadas usan
dobles y la prueba transaccional no confirma sus cambios.

## Corrección regresiva de cancelaciones

La revisión del PR #25 detectó que `chk_alerta_cancelaciones()`, creada en la
migración 03, seguía insertando el formato anterior de `notificaciones`. Como
`asunto` y `estado_reclamo` son obligatorios desde la 21, la tercera
cancelación podía fallar y revertirse junto con su alerta.

La migración incremental `22_corregir_alerta_cancelaciones.sql` reemplaza el
cuerpo de la función sin recrear el trigger. La alerta ahora conserva el estado
actual del reclamo y entra a la cola como `pendiente` con
`proximo_intento_en = now()`. La prueba transaccional optativa agrega tres
cancelaciones, comprueba que las primeras dos no alerten, que la tercera se
guarde y produzca una única notificación completa, y finaliza con `ROLLBACK`
sin invocar SMTP.

La corrección se aplicó con autorización al Supabase compartido el
**14/09/2026 (Argentina)**, con historial
`20260915005037_hu10_corregir_alerta_cancelaciones`. La prueba focalizada real
obtuvo **1 aprobación**: no persistió cancelaciones ni notificaciones y no
realizó conexiones SMTP.
