# HU12 — Notificación al actor responsable

Fecha de validación inicial: **17/09/2026**. Revisión del PR #26: **21/09/2026**.

Historia: **AARI-135**

## Decisión funcional

Después de una clasificación automática confiable, AARI identifica un único
actor responsable:

- gasto ordinario: inquilino;
- gasto extraordinario: propietario;
- expensa: inmobiliaria.

El reclamo pasa a `Pendiente de respuesta del responsable`. Si la
clasificación requiere revisión manual, conserva el circuito `Escalado` y no
genera esta solicitud automática.

La notificación inicial se persiste en la misma transacción que la
clasificación. El envío se intenta después del commit mediante la bandeja de
salida existente; un fallo de SMTP no revierte el reclamo. Cuando el actor es
el inquilino se consolida el aviso genérico de cambio de estado con la
solicitud de acción para no enviar dos mensajes equivalentes.

## Plazos y vencimiento

Los valores se leen de `configuracion_sistema`:

- `plazo_recordatorio_horas`: 48 horas por defecto;
- `plazo_escalado_horas`: 24 horas adicionales por defecto.

Al cumplirse el primer plazo se encola un recordatorio. A las 72 horas totales
sin respuesta, el reclamo pasa a `Pendiente de respuesta - vencido` y se avisa
al operador asignado. Si no hay uno activo, se elige el primer operador activo
y, como último respaldo, un administrador activo.

Los procesos concurrentes reclaman trabajo con `FOR UPDATE ... SKIP LOCKED` y
cada evento tiene una clave de idempotencia. WhatsApp permanece como un puerto
del sistema: la preferencia puede persistirse, pero su integración real
corresponde a una historia posterior. HU12 reutiliza email y la bandeja de
salida de HU10.

## Persistencia y seguridad

`23_notificaciones_actor_responsable.sql` incorpora:

- `propietarios.canal_notificacion`;
- `notificaciones.tipo_evento` y `clave_idempotencia`;
- la tabla privada `reclamo_responsables`, con plazos, contacto resuelto,
  índices parciales y control de integridad;
- compatibilidad de los triggers existentes de estados y cancelaciones con el
  nuevo contrato de la bandeja de salida.

La tabla nueva tiene RLS habilitado y permisos revocados para `anon` y
`authenticated`. El acceso continúa exclusivamente por FastAPI. La migración
no incluye datos personales, credenciales ni valores de `.env`.

## Validaciones

### Correcciones de revisión del PR #26

La clasificación automática es una operación inicial: solo admite reclamos en
`Recibido` o `Clasificación pendiente`, sin clasificación ni solicitud de
responsable previas. Una repetición o un estado avanzado devuelve HTTP `409`
antes de invocar el modelo. La condición se vuelve a comprobar con el reclamo
bloqueado al persistir, por si cambió durante la ejecución del grafo.

Se eligió rechazar la reclasificación automática en lugar de reemplazar al
responsable porque ese reemplazo necesitaría un flujo explícito para cancelar
avisos anteriores, resolver respuestas en curso y recalcular plazos. Así se
conservan juntos el tipo de gasto, el actor, el contacto, los plazos, el
historial y las notificaciones originales. Se eliminó el `ON CONFLICT DO
NOTHING` que ocultaba la conservación de un responsable incompatible.

Los recordatorios y vencimientos ahora bloquean tanto `reclamos` como
`reclamo_responsables` con `FOR UPDATE OF r, rr SKIP LOCKED`. Una autorización
en curso impide que el worker tome ese reclamo. Si el worker obtiene primero
el bloqueo, la autorización espera a que termine su transacción. Además,
`UPDATE ... RETURNING id` debe confirmar el cambio a vencido antes de crear
su alerta o marcar `escalado_en`; cero filas modificadas no genera efectos.

Estas correcciones no requieren migraciones, dependencias nuevas ni cambios
de configuración de la aplicación. La migración 23 ya aplicada no se modificó.

Se agregaron 12 pruebas con PostgreSQL 17 local y datos sintéticos: repetición,
cambio ordinario/extraordinario en ambas direcciones, expensa a ordinario,
clasificaciones simultáneas, estado modificado durante la clasificación,
clasificación inicial pendiente, autorización concurrente con recordatorio o
vencimiento, bloqueo entre selección y actualización y transición de cero filas.
También se agregaron siete casos HTTP para verificar el `409` sin envíos ni
persistencia y evitar llamadas innecesarias al modelo.

Para reproducirlas, usar una instancia PostgreSQL **local y dedicada a pruebas**,
con los roles `anon` y `authenticated` existentes y un usuario con permisos de
creación de bases y de las extensiones de las migraciones. Desde `backend/`:

```powershell
$env:AARI_TEST_POSTGRES_URL = 'postgresql://aari_test@127.0.0.1:55426/postgres'
$env:DATABASE_URL = $env:AARI_TEST_POSTGRES_URL
python -m pytest tests/test_responsible_actor_postgres.py -q
python -m pytest -q
```

La URL es un ejemplo de una instancia aislada; no copiar credenciales reales
en este documento ni usar Supabase. Cada caso crea una base con nombre
`aari_pr26_<uuid>`, aplica las migraciones necesarias y elimina exclusivamente
esa base al terminar. Sin `AARI_TEST_POSTGRES_URL`, estos casos se omiten.

Resultado de la suite completa el 21/09: **334 aprobadas, 26 omitidas**, con
una advertencia de deprecación del adaptador `datetime` de SQLite. Incluye los
12 casos PostgreSQL y no presenta fallos. Las omisiones corresponden a pruebas
optativas de servicios/configuración externos. Como control de regresión,
siete de los casos nuevos se ejecutaron contra el repositorio anterior
(`5123ace`) y fallaron, reproduciendo los problemas reportados. Esta revisión
no consumió Gemini, no envió correo real y no modificó Supabase compartido.

### Evidencia de la validación inicial

Pruebas focalizadas:

```powershell
.\.venv\python.exe -m pytest tests/test_responsible_actor_migration.py tests/test_responsible_actor_notifications.py tests/test_classification_graph.py tests/test_classification_integration.py tests/test_reclamos_api.py tests/test_claim_notifications.py tests/test_claim_notifications_repository.py -q
```

Resultado: **47 aprobadas**.

Suite completa del backend: **315 aprobadas, 25 omitidas**. Las omisiones son
pruebas optativas que requieren servicios externos o configuración específica;
no hubo fallos.

QA transaccional en Supabase:

```powershell
$env:RUN_SUPABASE_INTEGRATION='1'
.\.venv\python.exe -m pytest tests/test_responsible_actor_supabase_integration.py -q
```

Resultado transaccional: **4 aprobadas antes y después de aplicar la
migración**. Se validaron los tres actores, las notificaciones esperadas, los
plazos 48/72 horas, el recordatorio y el cambio a vencido. Antes de la
aplicación, el esquema se creó temporalmente dentro de la transacción de QA;
después se repitió el recorrido sobre la estructura instalada.

El cierre agregó una quinta prueba optativa del recorrido HTTP completo con
clasificación controlada y SMTP real: el endpoint persistió el actor
inquilino, reclamó la notificación, el proveedor aceptó el correo en el primer
intento y la bandeja registró `enviado`. La prueba terminó con `ROLLBACK`, no
dejó registros ni cambios en reclamos reales y no documenta el destinatario.

No se realizó una llamada real a Gemini porque el entorno local no tiene
`GEMINI_API_KEY`. El grafo y su mapeo de los tres tipos de gasto están cubiertos
con dobles deterministas; la validación real del proveedor queda disponible
cuando se configure esa variable, sin formar parte del alcance nuevo de HU12.

La revisión posterior confirmó RLS activo, ausencia de lectura para `anon` y
`authenticated`, funciones de trigger `SECURITY INVOKER` con `search_path`
vacío y cero notificaciones históricas sin `tipo_evento`. Los avisos del asesor
sobre RLS sin políticas e índices todavía no utilizados son informativos y
esperados: el módulo se consume por FastAPI y los índices acaban de crearse.
Permanecen advertencias anteriores a HU12 en `set_updated_at()` y
`rls_auto_enable()`; su corrección queda fuera del alcance para no modificar
infraestructura compartida sin una decisión específica.

## Estado y pendientes

- La migración 23 se aplicó con autorización al Supabase compartido AARI el
  **17/09/2026 (Argentina)** y quedó registrada como
  `20260917200108_hu12_notificaciones_actor_responsable`. No repetirla al hacer
  pull.
- Implementación y correcciones disponibles para revisión en el
  [PR #26](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/26), rama
  `codex/AARI-135-notificacion-actor-responsable`. Pendiente aprobación y merge.
- El tiempo autorizado de la implementación se registró por separado en Jira;
  esta revisión no añade tiempo ni cierra actividades.
- El registro equivalente en Notion no pudo crearse porque el espacio alcanzó
  el límite de bloques del plan actual. Esta página conserva la decisión en el
  repositorio hasta que Notion vuelva a admitir escrituras. El intento del
  21/09 de registrar esta corrección volvió a recibir `403 restricted_resource`
  por ese mismo límite.
