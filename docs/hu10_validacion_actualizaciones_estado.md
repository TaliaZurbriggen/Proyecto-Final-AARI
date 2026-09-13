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

Resultados previos a publicar la corrección:

- backend: **295 aprobadas, 20 omitidas**;
- frontend: **100 aprobadas**;
- ESLint: aprobado;
- build de Vite: aprobado;
- pruebas focalizadas de seguimiento: **5 aprobadas**;
- pruebas focalizadas de notificación/migración/API: **17 aprobadas**.

La prueba de SMTP real queda fuera de este QA: las pruebas automatizadas usan
dobles y la prueba transaccional no confirma sus cambios.
