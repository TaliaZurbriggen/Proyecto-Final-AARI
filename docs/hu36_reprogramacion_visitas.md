# HU36 / AARI-365 — Reprogramación de visitas y reportes de ausencia

En el detalle de una visita confirmada, el inquilino o el proveedor seleccionado
puede proponer otro horario con un motivo breve. La otra parte puede aceptarlo
o rechazarlo. El solicitante puede retirar su propuesta. El horario confirmado
sigue vigente hasta que la contraparte acepte. La conversación de HU33 permite
acordar qué proponer. La fecha cambia mediante la acción de aceptación de HU36.

## Reglas acordadas

- Una propuesta activa con un horario concreto simplifica la aceptación y
  permite conservar todas las decisiones. Vence a las 24 horas o al llegar
  la primera de las dos fechas, lo que ocurra antes. Tras retiro, rechazo o
  vencimiento, se admite otra mientras el horario vigente siga en el futuro.
- Desde la hora programada, cada participante puede registrar un reporte por
  horario confirmado. Puede indicar que la visita no se realizó o que la otra
  parte no asistió. El historial conserva las dos versiones con su autor y
  sus observaciones, aunque discrepen. La agencia con acceso puede consultarlas.
  El propietario conserva acceso a la fecha y los avisos de logística que le
  correspondan. El reporte no cambia el estado del reclamo ni la selección.
- El alcance cubre al proveedor seleccionado por HU20 y la visita de HU23.
  El calendario del proveedor externo de HU18 tiene su propio recorrido.

## Persistencia y operación

La migración `20261111120000_hu36_reprogramacion_visitas.sql` agrega propuestas,
reportes privados y una revisión del horario. El backend verifica cuenta,
perfil, selección, reclamo y visita vigentes bajo las reservas existentes.
Cada solicitud lleva el UUID de la coordinación, la versión esperada y una
clave de reintento. La decisión identifica explícitamente la propuesta.

La aceptación conserva la misma visita y actualiza su fecha, la del reclamo,
el historial y los avisos en una sola transacción. Cada confirmación y cada
recordatorio de 24 h o 2 h queda ligado a la revisión de horario. Se invalidan
los avisos pendientes o reservados del horario sustituido y se verifica la
revisión antes de entregar. Los avisos que ya se enviaron quedan en el historial.
El plazo de recordatorio se cuenta desde la nueva confirmación y se omiten los
recordatorios que ya habrían correspondido antes de esa confirmación.

`AARI_VISITS_ENABLED` sigue controlando la coordinación. Con el esquema de
HU23, la app conserva el flujo anterior. Al aplicar HU36, actualizar primero
los procesos que atienden visitas y los que procesan sus avisos para que todos
interpreten las revisiones de horario. Las pruebas de esta entrega usan datos
sintéticos, PostgreSQL local y envíos simulados. La migración y la verificación
del entorno compartido quedan pendientes.

## Cómo probar localmente

1. Confirmar una visita de prueba con un inquilino y un proveedor seleccionado.
2. Proponer otra fecha desde **Visitas** y comprobar que la fecha anterior siga
   vigente. Con la contraparte, rechazar o aceptar la propuesta. La fecha del
   reclamo y el historial deben reflejar la aceptación.
3. Con una visita de prueba cuyo horario ya pasó, registrar un reporte por rol.
   Comprobar que se vean ambos reportes y que el reclamo siga programado.

Pruebas focalizadas con `AARI_TEST_POSTGRES_URL` apuntando a una instancia
local descartable. Desde `backend/`:

```powershell
python -m pytest tests/test_visit_followups_postgres.py tests/test_visits.py tests/test_visits_postgres.py -q
```

Desde `frontend/`:

```powershell
npm test -- src/features/visitas/VisitCoordinationPage.test.jsx
npm run lint
npm run build
```

## Evidencia local

- Tanda de visitas con PostgreSQL y contratos HTTP, 57 pruebas aprobadas.
  Repetición de HU36 con la regresión de rollback agregada, 7 aprobadas.
  Las tandas se solapan.
- Regresión general del backend sin PostgreSQL, 1.257 aprobadas y 650 omitidas
  en esa ejecución. Las pruebas de PostgreSQL se ejecutaron por separado.
- Frontend, 11 pruebas de coordinación aprobadas y lint y build correctos.
  En navegador con datos simulados se verificaron escritorio, móvil, foco
  visible y aceptación con teclado. En móvil el área de contenido de 375 px
  no tuvo desborde horizontal.
