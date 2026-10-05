# HU14 — Propuesta de implementación de derivación de expensas

Preparada y **aprobada el 07/10/2026**. Implementación de desarrollo terminada;
evidencia, migración y pendientes en [hu14_derivacion_expensas.md](hu14_derivacion_expensas.md).
Jira: [AARI-157](https://taliazurbriggen.atlassian.net/browse/AARI-157),
asignada a Tobías; revisión final de entrega pendiente de Talía. Commit/push/PR
autorizados el 07/10 y [PR #30](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/30)
publicado. Doce subtareas listas; HU En curso hasta revisión/integración.
Seguimiento y evidencias en el documento de ejecución.
Base revisada: `main` en `80afb67`. Estimación del Sprint: **5 HH**,
distribuidas entre las 12 subtareas; los 30 puntos académicos originales se
conservan. El tiempo real se registra solo después de confirmación del usuario.

## Objetivo y límites

Cuando una clasificación confirmada indica expensa, informar a la inmobiliaria
con un reporte estructurado, permitir su seguimiento privado y comunicar al
inquilino que la inmobiliaria evaluará cómo proceder. AARI no autoriza gastos,
no selecciona proveedores ni da por reparado el problema por enviar un correo.

Incluye reporte, correo, configuración del destinatario, tres intentos de
entrega, transición de estado, aviso al inquilino, listado/detalle, notas
internas, alertas y auditoría. No incluye WhatsApp Business (HU19), autorización
de gastos (HU16), asignación de proveedores (HU15), métricas (HU26), despliegue
ni modificaciones a la lógica de extracción contractual de HU30.

## Base existente y reutilización

- HU10 aporta worker, bandeja durable de `notificaciones`, reservas de entrega,
  tres intentos espaciados 60 segundos, historial y avisos al inquilino.
- HU12 aporta responsable inmobiliaria, clave de idempotencia y contacto de
  `configuracion_sistema.correo_contacto_inmobiliaria`. Hoy genera un aviso
  genérico y deja también las expensas pendientes de respuesta del responsable.
- Ya existen `notas_internas`, `configuracion_sistema` y el estado
  `Derivado a inmobiliaria (expensa)`. No hay que duplicar esas estructuras.
- HU11 aporta patrones de filtros, paginación de 20, detalle y fechas argentinas.
- SMTP y autenticación se reutilizan; no se necesitan claves o variables nuevas
  en `.env` ni un proveedor de correo adicional.

## Flujo propuesto y decisiones a aprobar

1. Clasificación confirmada como expensa y sin escalado pendiente: guardar
   clasificación, responsable, copia del reporte y una única intención de
   correo en la misma transacción. El grafo mantiene su rol de decidir;
   no envía SMTP ni escribe datos externos.
2. El reporte incluye número/ID, fechas, ubicación/unidad, descripción,
   urgencia, identidad de contacto necesaria del inquilino, clasificación,
   fundamento, origen agente/humano y confianza cuando corresponda. No inventa
   campos faltantes; la clasificación humana no muestra confianza de LLM.
   No se incluyen DNI, contraseñas, notas internas o URLs públicas de adjuntos.
3. Usar un correo específico de reporte **en reemplazo del aviso genérico
   HU12 para expensas**, evitando dos avisos iniciales a la inmobiliaria.
   Incluir aclaración de evaluación pendiente y enlace protegido al detalle.
4. Enviar en segundo plano, fuera de transacciones SQL. Tres intentos totales:
   el inicial y dos reintentos, con 60 segundos entre intentos fallidos,
   persistidos en la base; no mantener la petición web esperando el correo.
5. Solo después de que SMTP acepte el reporte y se registre un resultado
   vigente, pasar a `Derivado a inmobiliaria (expensa)`. Esto no asegura que
   el correo llegue a bandeja de entrada o sea leído. El cambio de estado y
   la confirmación de entrega se registran juntos, sin sobrescribir estados
   más avanzados que otro usuario haya guardado mientras se enviaba.
6. La transición dispara el aviso existente de HU10 al inquilino, con lenguaje
   sencillo: la inmobiliaria evaluará el problema. No se envía un segundo aviso
   duplicado, ni se incluyen fundamentos internos o notas de administración.
7. Si fallan los tres intentos, conservar la clasificación y el estado previo
   (`Pendiente de respuesta del responsable`); mostrar **Reporte no enviado**
   a administración/operación, con intentos y error seguro. No informar al
   inquilino que ya se derivó ni simular éxito. Si falta o es inválido el correo
   de contacto, mostrar **Configuración pendiente** sin consumir intentos SMTP.
8. Separar las expensas del circuito HU12 de recordatorio y vencimiento por
   respuesta del responsable: su gestión pasa al módulo de inmobiliaria, no
   al flujo de elección de proveedor. No alterar ordinarios/extraordinarios.

No habrá reenvíos masivos, cambio retroactivo de destinatarios ni recuperación
automática ilimitada de fallos. Los reportes ya encolados conservan la copia y
el destinatario con el que se crearon; cambiar el correo de configuración
afecta reportes nuevos. El tratamiento de históricos se indica más abajo.

## Panel y permisos

- Nueva sección **Expensas**, bajo la única navegación superior existente,
  con listado `/expensas` y detalle `/expensas/{reclamo_id}`. No se crea otra
  cabecera o un layout lateral ni se modifica el diseño del Home de HU31.
- Listado con número, unidad, fecha, estado del reclamo y entrega. Vista
  principal de derivados; sección/filtro de pendientes y fallidos para que
  los problemas de correo no desaparezcan del panel. Propiedad y rango de
  fechas de ingreso, combinables; totales antes de paginar, 20 por página.
- Detalle con reporte, intentos, canal/destinatario/fecha de envío y notas
  internas. Notas de texto plano de 1 a 1000 caracteres, con usuario de la
  sesión y timestamp de servidor. Se agregan; no se editan ni borran en HU14.
- Administración y operadores activos que completaron el primer ingreso
  pueden consultar expensas y agregar notas. **Solo administración** puede
  consultar/cambiar el destinatario en la configuración.
- Inquilinos y propietarios no reciben el reporte completo, contactos ajenos
  o notas internas. El inquilino conserva su seguimiento HU10/HU11.
- Usar `PageContainer`, `PageHeading`, `FormField`, `Button`, `StatusBadge`,
  `AlertMessage`, `LoadingState`, `EmptyState`, tokens y CSS Modules de AARI.
  Móvil: filtros apilados y tabla adaptada, sin desborde; teclado, foco y
  etiquetas visibles, estados de carga/vacío/error y rechazo de datos obsoletos.

## API y persistencia previstas

- `GET/PUT /configuracion/correo-inmobiliaria`: esquema de email validado,
  acceso administrativo, sin devolver el resto de la configuración.
- `GET /expensas`: filtros de propiedad, fecha y situación de entrega.
- `GET /expensas/{id}`: detalle privado, reporte y auditoría de entrega.
- `POST /expensas/{id}/notas`: agrega una nota con autor autenticado.
- Reutilizar `notificaciones` para estado de envío, intentos y destinatario,
  `notas_internas` para notas y `reclamo_historial_estados` para transiciones.
- Proponer una tabla pequeña `reclamo_derivaciones_expensa`, única por reclamo,
  para congelar el reporte y vincular la notificación, incluso cuando aún no
  exista un contacto válido. No duplica el contador de intentos ni el estado
  de envío de `notificaciones`; evita regenerar el reporte con datos cambiados.
- Migración **aditiva**: tabla/FK, tipo de evento de reporte, índices y
  protección de notas/configuración; sin borrar o reclasificar reclamos.
  RLS y permisos de cliente revocados para información privada, conservando
  FastAPI como único acceso. No usar Supabase Auth para sustituir la sesión
  propia del proyecto. Referencia: [seguridad RLS de Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security).
- Reservar una versión única antes de crear la migración: HU30 ocupa 24/25 y
  HU13 propone 26, además de los dos archivos históricos con prefijo 23. No
  renombrar migraciones aplicadas ni ejecutar archivos mediante un glob ciego.
  Confirmar el orden por nombre completo e historial del entorno.

## Archivos previstos

Rutas nuevas orientativas; no existen aún y pueden ajustarse al aprobar:

- `backend/app/api/expensas.py`, `configuracion.py`;
  `backend/app/schemas/expensas.py`, `configuracion.py`;
  `backend/app/db/expensas.py`, `configuracion.py`;
  `backend/app/services/expense_notifications.py`, `expensas_service.py`.
- Integración mínima en `backend/app/db/reclamos.py`,
  `backend/app/main.py` y los contratos/tests de notificaciones y clasificación.
  Reutilizar el worker; completar el resultado vigente de envío de forma
  transaccional, sin copiar el circuito completo de HU12.
- Migración de versión única en `backend/migrations/`, su README y pruebas
  unitarias/HTTP/PostgreSQL en `backend/tests/`.
- `frontend/src/features/expensas/` para API, páginas, CSS Modules y tests;
  registro de rutas en `frontend/src/App.jsx` e integración mínima en layouts.
  Configuración del destinatario dentro del módulo, sin rediseñar HU31.
- `docs/hu14_derivacion_expensas.md`, README y seguimiento del Sprint.

## Cobertura de las 12 subtareas

| Subtarea | Entrega propuesta | Estimación existente |
| --- | --- | --- |
| AARI-158 | Reporte estructurado y copia persistida | 30 min |
| AARI-159 | Correo de reporte y aclaración de evaluación | 20 min |
| AARI-160 | GET/PUT administrativo de contacto | 20 min |
| AARI-161 | Envío durable y tres intentos de 60 segundos | 30 min |
| AARI-162 | Aviso simple al inquilino reutilizando HU10 | 20 min |
| AARI-163 | Transición después de aceptación SMTP registrada | 10 min |
| AARI-164 | Listado, detalle, filtros y paginación | 40 min |
| AARI-165 | Notas privadas con autor y fecha | 30 min |
| AARI-166 | Alerta de fallo/configuración pendiente | 20 min |
| AARI-167 | Canal, destinatario y fecha en auditoría de envíos | 10 min |
| AARI-168 | Pruebas del recorrido exitoso | 40 min |
| AARI-169 | Pruebas de fallo y agotamiento de intentos | 30 min |
| Total | Estimación, no tiempo ya trabajado | 5 HH |

## Validación y entrega

1. Tests de reporte/plantillas, permisos por rol, email inválido, notas,
   filtros argentinos, paginación y privacidad de respuestas.
2. Reloj y SMTP simulados: éxito inicial, éxito en segundo/tercer intento,
   tres fallos, falta de contacto y caída/reanudación del worker. No dormir
   minutos reales en la suite; no consumir Gemini ni SMTP real.
3. PostgreSQL real **local y descartable**: transacciones, reservas vencidas,
   resultado tardío, dos workers, idempotencia, cambios de estado concurrentes,
   rollback, RLS/permisos e índices. El repositorio local preparado en HU11
   puede utilizarse sin tocar Supabase.
4. Regresiones HU10/HU11/HU12 y, después de integrarlo, clasificación humana
   HU13: una expensa humana debe generar el mismo reporte sin pasar por el LLM.
5. `python -m pytest -q`; frontend `npm run lint`, `npm run test -- --run`
   y `npm run build`; navegador escritorio/móvil y recorrido administrativo.
6. Aplicación de migración al Supabase compartido y prueba de correo real
   **requieren autorización específica posterior**, entorno y destinatario
   acordados. La aprobación de este plan no implica enviar correos a terceros.
7. Diff/formato/secretos, documentación, commit/push/PR solo con autorización;
   revisión de Talía antes de merge. Horas/minutos solo los confirmados por el
   usuario. Notion se sincronizará cuando permita escribir; preservar ADR local.

## Dependencias, históricos y riesgos

- Se puede implementar la parte aislada desde `main`, sin fusionar ahora
  PR #28/#29 ni cambiar sus ramas. Talía modifica `db/reclamos.py`, el grafo
  y navegación: integrar lo ya aprobado cuando llegue a main, conservar sus
  cambios y volver a validar; no reemplazar esos archivos completos.
- La entrega final debe probar el enlace con HU13/HU31 cuando estén integrados.
  Hasta entonces puede validarse el camino automático, no afirmar que la
  integración humana o el Home estén terminados.
- No disparar correos ni cambios de estado retroactivos durante la migración.
  Expensas antiguas aparecen con el estado/auditoría que realmente poseen;
  cualquier reenvío o conversión de históricos se evalúa por separado.
- SMTP no garantiza exactamente una entrega ni lectura: un envío aceptado
  seguido de una caída antes de guardar el resultado puede repetirse. Usar
  idempotencia/reservas para minimizarlo y documentar ese límite, no prometer
  ausencia absoluta de duplicados.
- Hay una dependencia de coordinación por versiones de migración y por los
  archivos compartidos. No se aumenta ni se cierra el Sprint automáticamente;
  su fecha prevista llegó, pero siguen HU pendientes.

La aprobación debe confirmar especialmente: **Derivado solo después de SMTP
aceptado**, estado previo conservado ante fallo, separación de recordatorios
HU12, permisos de operadores/notas y ausencia de envíos retroactivos.
