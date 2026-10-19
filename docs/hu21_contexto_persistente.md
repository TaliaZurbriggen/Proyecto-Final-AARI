# HU21 — Contexto persistente del agente (AARI-229)

## Estado y alcance

Propuesta aprobada el 11/10/2026. Rama `codex/AARI-229-contexto-persistente`
desde main `fb3a496`. Base implementada localmente; **HU21 sigue En curso**.
Commit, push y PR de esta base autorizados el 14/10/2026, para revisión de Talía;
no se autorizaron merge ni cierre de HU21. No se registró tiempo trabajado.
La previsión de Jira es 6 HH, independiente del tiempo real que confirme el usuario.

Esta entrega conserva el contexto de un reclamo **ya clasificado** y permite
retomarlo sin volver a clasificar ni repetir decisiones. No crea un chat nuevo,
no interpreta mensajes con un LLM, no solicita presupuestos ni autoriza gastos.
HU15 puede buscar candidatos desde Recibido por su propio circuito: no depende
de iniciar esta sesión. No se modificó su rama ni se incorporó código no publicado.

El grafo cubre los puntos de espera y salida del flujo del Sprint, pero sus
acciones pertenecen a HU16/HU17/HU18/HU19/HU20/HU23/HU24. Las cinco pruebas
multi-turno iniciales usan **adaptadores de dominio simulados**; no acreditan
la integración real de esas HU. AARI-236 y AARI-237 quedan pendientes.
La etapa esperando_seleccion_presupuesto está reservada en el contrato:
su activación se acordará con el resultado durable de HU19, no se infiere
que cualquier presupuesto recibido cierre la recepción.

## Decisiones técnicas

- Se reutiliza `sesiones_agente`, con una fila única por reclamo, para el
  snapshot tipado y versionado del dominio. Su existencia anterior no equivalía
  a tener checkpointing implementado.
- Se adopta **PostgresSaver oficial 3.1.2**, en vez de memoria volátil o un
  formato de checkpoint propio. La migración materializa explícitamente el
  esquema 0..9 de esa versión en `aari_coordinacion`. No se ejecuta
  `setup()` ni DDL al arrancar FastAPI.
- La conexión psycopg de la transacción se comparte con PostgresSaver.
  `durability="sync"` termina los checkpoints antes de guardar la sesión y
  confirmar la transacción. Un fallo posterior revierte ambos.
- El estado de `reclamos` es la fuente de verdad del negocio: el grafo
  proyecta hechos confirmados, no escribe autorizaciones, selecciones ni visitas.
  Un GET informa si el snapshot necesita sincronización y el estado actual,
  sin renovar actividad ni escribir checkpoints.
- Se valida nuevamente la cuenta activa y primer ingreso completado.
  Administración/operación acceden por rol; propietario e inquilino sólo a
  reclamos vinculados a su usuario actual. No se confía en perfiles enviados
  por el cliente, ni se expone un endpoint de eventos arbitrarios.
- Orden de locks: usuario, reclamo, sesión. Los workers reservan el reclamo
  con SKIP LOCKED y no esperan un destinatario bloqueado. La invocación del
  grafo es determinista y no mantiene locks mientras consume una API externa.
- Evento UUID, fingerprint de la solicitud, versión esperada e intento UUID.
  Un reintento idéntico devuelve contexto sin efectos; reutilizar el UUID
  con otro contenido, una versión antigua o un intento ajeno produce 409.
  La proyección detecta cancelaciones persistidas y renueva el intento.
  El historial resumido conserva hasta 20 identificadores, no datos de contacto.
  La deduplicación durable se conserva separadamente en la tabla de eventos.
- Sesiones y checkpoints tienen RLS y permisos revocados para PUBLIC,
  anon y authenticated. El esquema privado no se expone al Data API.
  Sólo el backend conecta a PostgreSQL. No se guardan claves en snapshots.

Referencia: [persistencia LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence)
y [memoria PostgreSQL](https://docs.langchain.com/oss/python/langgraph/add-memory).
Las guías de Supabase/PostgreSQL determinaron el esquema privado, la defensa
RLS y el orden de bloqueos. El changelog oficial se revisó antes de implementar.

## Contrato HTTP inicial

- GET `/reclamos/{uuid}/coordinacion`: snapshot, última interacción válida,
  `requiere_sincronizacion` y estado actual. Sin sesión creada: 404.
- POST `/reclamos/{uuid}/coordinacion/retomar`: acción deliberada, no polling.

Primera reanudación:

```json
{
  "evento_id": "UUID-nuevo-por-interaccion",
  "version_esperada": 0
}
```

Los valores de ejemplo son marcadores: se reemplazan por UUID reales de prueba.
Luego se envían `version_esperada` e `intento_id` obtenidos en la respuesta.
Reintentar la misma petición conserva su evento_id. Una interacción distinta
necesita otro. El servidor deriva la identidad de la cookie y no acepta
`autorizar`, `rechazar`, importes o selecciones en este cuerpo.
Al retomar se lee otra vez el estado confirmado del negocio. Las etapas
terminales, expiradas o que requieren intervención rechazan la reanudación.

## Expiración

72 horas desde la última reanudación válida, inclusive. GET, sondeos,
duplicados y peticiones rechazadas no reinician el reloj.

En esta base el worker procesa únicamente los estados Clasificado/Autorizado
que proyectan espera de elección, sin vencimiento específico. No toca:

- autorización/respuesta del responsable: HU12/HU16 poseen sus plazos;
- recepción de presupuestos y confirmación de disponibilidad: sus módulos
  todavía deben aportar el vencimiento específico;
- visita programada, reclamos finalizados, rechazo, proveedor externo,
  escalados/gestión manual y expensas de HU14.

Se confirman juntos Sesión expirada, historial, snapshot/checkpoint y un aviso
durable al operador habilitado (o administrador como fallback). La alerta usa
una clave idempotente; el aviso al inquilino reutiliza el trigger existente.
SMTP no se ejecuta aquí: el outbox existente entrega y reintenta por separado.
Sin destinatario habilitado se conserva el caso y se reintenta después;
no se inventa un contacto ni se afirma haber enviado una alerta.

## Migración y configuración

`backend/migrations/20261011222710_hu21_contexto_persistente.sql`, generada
mediante Supabase CLI 2.120.0 y trasladada a la carpeta convencional.
Requiere las migraciones del Sprint 3 y las tablas del módulo de coordinación.
Conserva archivos/historial aplicados; no cambia casos ni encola mensajes
retroactivos. Si hay contextos no vacíos anteriores, se detiene para revisarlos,
sin sobrescribirlos ni inferir una transformación.

El preflight compara objetos e historial en ambas direcciones, RLS, permisos
y la versión del esquema de checkpoints. Aplicación e historial son atómicos.

```powershell
python scripts/check_coordination_postgres.py --mode check
python scripts/check_coordination_postgres.py --mode apply
```

Por defecto sólo admite loopback. Un destino compartido requiere autorización
humana y `--allow-shared` explícito.

**Aplicada con autorización al Supabase AARI de desarrollo el 11/10/2026**,
historial `20261011222710_hu21_contexto_persistente`. La aplicación compartida
usó `scripts/apply_hu21_shared.py`: verifica la referencia del proyecto,
lee credenciales locales sin mostrarlas y compara conteos/huellas de las
33 tablas públicas antes/después dentro de una transacción REPEATABLE READ.
Registra DDL e historial juntos; una diferencia revierte la transacción.
Una comparación posterior independiente por MCP confirmó que las 33 tablas
conservaron sus filas/huellas, incluidas las tablas de HU15.
No repetir la migración al actualizar de rama o por integrante.

Verificación real después de confirmar la transacción de la migración:

- PostgreSQL de Supabase **17.6**, frente al PostgreSQL local de pruebas 17.11.
- Cinco tablas privadas más sesiones con RLS; anon/authenticated sin permisos
  CRUD ni USAGE/CREATE sobre el esquema privado.
- Versiones de checkpoints 0..9, columnas generadas, índices y FK verificadas;
  todas las restricciones revisadas están validadas.
- Preflight y lectura real de PostgresSaver 3.1.2 aprobados en transacción
  READ ONLY. Thread de prueba inexistente devuelve vacío. No se llamó setup.
- Cero sesiones/contextos/eventos/checkpoints de negocio creados; cero envíos,
  workers apagados, sin SMTP, WhatsApp, Gemini ni cambios a Storage.
- La prueba de escritura compartida se autorizó por separado y se completó
  con rollback obligatorio el 14/10/2026; resultado y límites debajo.

Se mantuvieron los avisos de seguridad previos: search_path mutable en
`public.set_updated_at` y ejecución de la función SECURITY DEFINER
`public.rls_auto_enable` para anon/authenticated. No son hallazgos nuevos de
HU21, no se corrigieron fuera de alcance ni se afirma una auditoría completa.
Referencias de remediación:
[search_path](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable),
[ejecución anon](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable),
[ejecución authenticated](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).

Los avisos nuevos son informativos:
[RLS sin políticas](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
en cinco tablas deliberadamente privadas (permisos de clientes revocados), e
[índices aún no utilizados](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index)
porque todavía no hay sesiones. No se abrieron políticas para silenciar avisos,
ni se retiraron índices por no tener carga inicial. Los 16 avisos anteriores
de FK sin índice no aumentaron.

El parser .env informó líneas no válidas 1 y 12 en archivos existentes.
DATABASE_URL se leyó correctamente y su destino fue validado. No se mostraron
valores ni se modificaron esos .env; su limpieza queda fuera de esta acción.

El aplicador requiere el host directo exacto del proyecto o el dominio oficial
del pooler con su usuario de proyecto exacto; rechaza destinos parecidos.
Después de la aplicación se aprobaron **28 pruebas locales de guardas/API**
(1,13 s), incluidas siete nuevas del runner. Verifican autorización explícita,
destino erróneo/parecido, configuración ausente o malformada sin revelar valores.
`pip check` sin conflictos. Esta pasada no se suma a las 856 pruebas de
la base ni se presenta como otra suite completa con PostgreSQL.

Se mantienen DATABASE_URL y SMTP existentes. No hay nuevas claves.
Nueva variable en backend/.env.example:

```env
COORDINATION_WORKER_ENABLED=false
```

Apagada por defecto hasta verificar migración e integración. Instalar
`backend/requirements.txt` incorpora las dependencias fijadas de checkpoints
y psycopg3, manteniendo psycopg2 para los módulos actuales.
No se modificó el .env real ni el Python global. El entorno virtual y la rama
de trabajo están en el checkout aislado `.codex-hu21`; la copia principal
conserva su branch y cambios.

## QA de escritura compartida — 14/10/2026

**12 casos aprobados** contra PostgreSQL 17.6 de Supabase AARI, sin DDL,
llamadas al modelo, SMTP, WhatsApp, Storage ni activación de workers.
Se usaron exclusivamente cuentas, contactos y reclamos ficticios propios.
Cada caso se ejecutó en un savepoint con rollback, dentro de otra transacción
REPEATABLE READ que también se revierte obligatoriamente. Se verifica que no
haya sesiones reales antes de probar los vencimientos. Los reclamos de prueba
usan número explícito: `nextval` no se revierte con una transacción.

Casos aprobados:

1. Escritura/lectura por las rutas HTTP y repetición idempotente del evento.
2. Recuperación con un repositorio y grafo nuevos desde PostgresSaver real.
3. Rechazo de versiones e intentos obsoletos sin escrituras.
4. Rechazo de un UUID de evento reutilizado con otro contenido.
5. Acceso del operador y participantes propios; rechazo de un tercero activo.
6. Revalidación de una cuenta ficticia desactivada después de iniciar el contexto.
7. Fallo inyectado después del checkpoint: snapshot y checkpoint se revierten.
8. Vencimiento general a las 72h: un único aviso pendiente, sin entregarlo.
9. Prioridad del plazo específico de respuesta/autorización.
10. Visita programada excluida de la expiración general.
11. Cancelación ficticia ya confirmada: nuevo intento e invalidación del anterior.
12. Expensa mantiene el circuito de HU14 y no abre una sesión de coordinación.

El runner confirmó `success=true`, `passed=12`, preservación de las 38 tablas
y numeración sin cambios. Una comparación **independiente por MCP** antes y
después confirmó conteos y huellas idénticos en las 33 tablas públicas y cinco
privadas. Al finalizar: cero sesiones, checkpoints y eventos de negocio,
secuencia de reclamos `last_value=1/is_called=true` sin cambios y cero
transacciones ajenas al comprobador abiertas. No se borraron filas para limpiar
la prueba: las escrituras ficticias desaparecieron por rollback.

La API se probó con TestClient y una identidad ficticia inyectada; el repositorio,
grafo y almacenamiento fueron reales. **No acredita login por cookie desde un
navegador ni un reinicio de proceso en Supabase**: se recrearon repositorio y
grafo dentro de la misma transacción. La recuperación en un proceso independiente
ya fue validada en PostgreSQL local. La expiración se invocó directamente con
reloj controlado, sin encender el worker ni entregar la notificación pendiente.
Tampoco acredita los flujos completos de selección, presupuesto, visita o
cancelación de las HU futuras: se proyectaron hechos ficticios persistidos.

Runner reproducible, desde `backend/`, **sólo con nueva autorización humana**:

```powershell
python -m scripts.qa_hu21_shared --authorized --env-root "C:\ruta\Proyecto-Final-AARI"
```

`--authorized` no sustituye el permiso humano. Se valida el destino exacto de
AARI y no se muestran credenciales. Las huellas de todas las columnas se agrupan
en una consulta por esquema para reducir viajes de red, sin omitir tablas.
El diagnóstico opcional `--diagnostic-after-seconds 60` muestra únicamente stacks,
no variables; sus avisos no son por sí mismos fallos de la prueba.

Las ejecuciones interrumpidas o sin salida final disponible no se contabilizan
como aprobadas. Antes de repetir se verificó que no quedaran transacciones ni
sesiones de prueba. La repetición completa del 14/10 acreditó los 12 casos.
No se atribuye la demora inicial a un bug HTTP.

Guardas locales del runner y regresión de grafo/API:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_coordination_shared_qa.py tests/test_coordination_migration_runner.py tests/test_coordination.py
python -m pip check
```

**36 passed**, 0,94 s en la repetición completa fuera del sandbox; la corrida
local anterior demorada se interrumpió y no se suma. Incluye ocho guardas de
préstamo de conexión/transacción, consultas de huellas de sólo lectura y
numeración sin `nextval/setval`. `pip check` sin conflictos. Es una pasada
focalizada posterior: no se suma a las 856 pruebas de la base ni se presenta
como otra suite completa. No hubo cambios productivos por este QA.

## Preparación de publicación — 14/10/2026

Commit funcional `ecd09ed`. Antes del push se incorporó el main publicado
`02479b9` (merge de HU15 / PR #33) en esta rama, sin modificar la copia principal.
El único conflicto de contenido fue `app/main.py`: se conservaron las rutas,
imports y workers de HU15 y se añadieron los de HU21. El diff contra main se
limita a los 20 archivos de esta base; el frontend y los archivos propios de
HU15 quedan idénticos a main. Se conservaron también los finales de línea de
los contenidos ajenos para evitar modificaciones sólo de formato.

El runner compartido ahora desactiva explícitamente también el worker y el
permiso de modelo de HU15, además de los de HU21/correo/contratos. No se volvió
a ejecutar el QA en Supabase ni se reaplicó la migración para publicar.

Validaciones después de integrar main, con workers y servicios externos apagados:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_coordination_shared_qa.py tests/test_coordination_migration_runner.py tests/test_coordination.py tests/test_provider_candidates.py tests/test_provider_candidates_agent.py
python -m pytest -q -p no:cacheprovider --tb=short --ignore=tests/test_provider_candidates_volume_postgres.py
python -m pip check
git diff origin/main --check
```

- Focalizadas HU21/HU15: **107 passed**, 1,35 s.
- Suite backend salvo volumen de HU15: **972 passed / 51 skipped**, 298,32 s,
  con PostgreSQL 17.11 local incluido. Las 18 advertencias son las preexistentes
  del adaptador datetime de SQLite. No se suman las focalizadas a ese total.
- No se repitió la suite de volumen de HU15 ni el frontend, que no cambian
  respecto de main. Las omitidas de servicios externos no se presentan como
  validadas. La pasada inicial con un rol local incorrecto se interrumpió;
  tras verificar el rol `aari_test`, la repetición completa aprobó sin cambios
  de código para resolver ese error de configuración.
- `pip check` sin conflictos. Diff y formato correctos; revisión de patrones de
  secretos en los 20 archivos, sin coincidencias. Sin `.env` real, documentos
  personales ni artefactos de QA en la entrega.
- Cero bases `aari_pr26_<uuid>` remanentes; PostgreSQL local detenido al terminar.

Las guías de Supabase/PostgreSQL orientaron la revisión de RLS, permisos privados
y bloqueos; la publicación no cambia esas decisiones ni activa procesos en la nube.
Publicar esta base no completa HU21: sigue pendiente la revisión y la integración
end-to-end indicada a continuación.

## Corrección de revisión P2 — 15/10/2026

Observación de Talía en [PR #34](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/34#pullrequestreview-5526811489):
una sesión antigua vacía (`estado_grafo={}`, versión 0) podía entrar al lote de
vencimientos. La validación del snapshot fallaba y revertía toda la transacción,
incluidos vencimientos válidos ya procesados. Se aprobó la corrección y su
commit/push en el mismo PR; no se autorizó merge ni cierre de HU21.

El selector de `expire_due()` ahora exige contexto no vacío y versión positiva
**antes de LIMIT**, para que las filas sin inicializar no ocupen el lote.
Tras bloquear la sesión se comprueban nuevamente esos requisitos, su condición
activa y su antigüedad. El snapshot se valida antes de modificar el reclamo.
Se conserva el orden de bloqueos y el filtro de sesión activa del índice parcial
existente, siguiendo las guías de Supabase/PostgreSQL, sin cambiar índices,
permisos ni la atomicidad del lote.

Las filas legadas se conservan intactas: no se borran, no se rellenan con un
contexto inventado ni se inicializan desde el worker. `resume()` sigue siendo
la acción que inicializa una sesión con versión 1 y actividad actualizada.
No se cambió la migración aplicada ni se requiere una nueva; tampoco hay
dependencias, configuración, frontend o modificaciones en HU15.

Se agregó una regresión PostgreSQL con dos unidades e inquilinos ficticios
distintos, respetando la restricción de un reclamo activo por unidad. Ocho
variantes combinan Autorizado/Clasificado, límites 1/20 y sesión vacía antes o
después de la válida. Verifican vencimiento de la válida, repetición sin
duplicar el aviso pendiente, preservación completa del reclamo/sesión vacíos,
cero checkpoints/eventos para la vacía y su posterior inicialización normal.

La primera preparación de datos intentó compartir unidad/inquilino y falló
por la restricción de unicidad: no se contabiliza como reproducción del bug.
Corregido sólo el fixture, la prueba previa al arreglo falló exactamente con
`ValidationError` al validar `{}` en `expire_due()`. Tras el cambio, las ocho
variantes aprobaron: **8 passed / 25 deselected**, 63,94 s. Son pruebas locales,
no validaciones nuevas de Supabase ni de entrega SMTP.

Comandos desde `backend/`, con PostgreSQL local dedicado y servicios externos
desactivados:

```powershell
python -m pytest -q -x -p no:cacheprovider --tb=short tests/test_coordination_postgres.py -k mixed_batch
python -m pytest -q -x -p no:cacheprovider --tb=short --ignore=tests/test_provider_candidates_volume_postgres.py
python -m pip check
git diff --check
```

Regresión backend posterior: **980 passed / 51 skipped**, 793,8 s,
con PostgreSQL 17.11 local. Las 18 advertencias SQLite son preexistentes.
No se repitió volumen de HU15 ni frontend; las omitidas externas no se presentan
como validadas. `pip check` sin conflictos.
Al terminar no quedaron bases ficticias y se detuvo PostgreSQL local de QA.
Las focalizadas no se suman a la pasada general. El worker de coordinación,
correo y llamadas externas permanecen apagados; no se ejecutó el QA compartido
ni se registraron horas de trabajo adicionales.

## Corrección de convivencia HU17/HU21 — 19/10/2026

Observación P2 de Talía en el [PR #34](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/34#issuecomment-6274123594),
referenciada también en #35 y #36. La autorización de HU16 abre en HU17 una
elección con 72 horas nuevas. HU21 sólo consultaba el plazo de HU12 cuando el
estado era `Pendiente de respuesta del responsable`; en `Autorizado` podía usar
la actividad antigua de la sesión y vencer anticipadamente la elección.

Reproducción local con los módulos reales de #34 (`ce76b88`), #35 (`eb5e0e9`)
y #36 (`6339c60`): inicializar coordinación 71 horas antes de autorizar, autorizar
por el repositorio HU16 y adelantar dos horas el reloj de coordinación. La
elección conservaba 70 horas disponibles, pero `expire_due()` devolvía 1.
La preparación inicial no tenía al operador ficticio habilitado: sólo reveló
que faltaba el plazo en la proyección; no se contabiliza como reproducción de
la transición. Con el operador habilitado se confirmó el vencimiento prematuro.

Decisión: **el plazo de la etapa vigente prevalece sobre la inactividad general**.
HU21 lee la elección pendiente sólo si coincide con reclamo, pedido responsable,
actor, tipo de gasto y estado de negocio. Expone ese plazo en el contexto sin
cambiarlo ni renovar actividad por GET. Incluso una elección ya fuera de plazo
se reserva al job específico de HU17: HU21 no genera otra transición ni aviso.
Se descarta reiniciar artificialmente la sesión al autorizar o copiar el job de
HU17, porque ocultaría la prioridad del dominio y duplicaría responsabilidades.

Los reclamos protegidos se excluyen **antes de LIMIT** y se vuelve a consultar
su dominio bajo bloqueo del reclamo. Así no ocupan el lote de otros vencimientos;
se conserva el orden reclamo → sesión y la corrección anterior de sesiones vacías.
La detección con `to_regclass` permite seguir usando la base HU21 sin HU17
instalado, sin DDL, tablas ficticias ni imports productivos entre PR.

Archivos: `app/db/coordination.py`, pruebas unitarias `test_coordination.py` y
regresión `test_coordination_provider_choice_postgres.py`. Esta última requiere
los módulos/fixtures reales de HU16/HU17: se omite explícitamente en la base
aislada de #34 y se ejecuta al combinar los tres PR, sin presentar una omisión
como prueba aprobada. Casos: 71+2 horas, proyección/sincronización del plazo,
ambos órdenes de ejecución y concurrencia de jobs, transición/aviso únicos,
segunda ejecución idempotente, lote de tamaño 1 y tres desajustes de etapa.

Comandos desde `backend/`, con PostgreSQL local dedicado, todos los workers y
permisos externos apagados y `SMTP_HOST` vacío:

```powershell
python -m pytest -q -x -p no:cacheprovider --tb=short tests/test_coordination_provider_choice_postgres.py tests/test_coordination.py
python -m pytest -q -x -p no:cacheprovider --tb=short --ignore=tests/test_provider_candidates_volume_postgres.py
python -m pip check
git diff --check
```

Validaciones locales posteriores:

- Focalizada conjunta: **34 aprobadas**, 24,17 s (ocho integradas y 26
  unitarias/contrato); incluidas en la pasada general, no se suman.
- Base aislada de #34: **74 aprobadas / una omitida**, 140,93 s. Incluye
  PostgreSQL, recovery en proceso independiente y la regresión de sesiones
  vacías; se omite sólo el módulo que requiere HU16/HU17 reales.
- Frontend combinado: **350 aprobadas / 38 archivos**, 101,46 s;
  `npm run lint` y `npm run build` correctos (build 2,99 s).
- OpenAPI: 56 rutas, con endpoints reales de autorización, elección y
  coordinación conservados; worker HU21 apagado. `pip check` correcto.
- Suite backend conjunta, salvo volumen de HU15: **1068 aprobadas / 51
  omitidas**, 481,41 s, con PostgreSQL 17.11 local. Conserva las 18 advertencias
  SQLite preexistentes; incluye las 34 focalizadas y no se suman aparte.

Las preparaciones interrumpidas por directorio temporal sin crear y por ejecutar
la prueba de subproceso fuera de `backend/` no se contabilizan como aprobadas; se repitieron
con el directorio creado y el cwd correcto. No se repite volumen de HU15 ni
se presentan pruebas omitidas de canales externos como validadas.
Conteo final: cero bases ficticias remanentes; PostgreSQL local de QA detenido.
Diff/formato y búsqueda de patrones de secretos/contactos reales correctos.

La combinación existe sólo en una rama local de QA iniciada desde main
`02479b9`; no se fusionan PR remotos ni se incorpora HU17 en la rama HU16.
Los conflictos de `README.md` y `backend/app/main.py` se resolvieron sólo allí,
conservando documentación, routers de HU16/HU17/HU21 y los cuatro workers
existentes. Al integrar de verdad hay que conservar esa unión y repetir las
pruebas sobre el resultado final. Orden: #35 primero; luego #36 con base main y
diff revisado. La convivencia con #34 no se acredita sólo por aprobar una base.

Sin nuevas migraciones, dependencias, `.env` ni cambios productivos de frontend;
sin Supabase, SMTP, WhatsApp o LLM reales. `COORDINATION_WORKER_ENABLED=false`
sigue siendo el valor por defecto y no se activa. Esta corrección parcial de
AARI-345 **no completa** los cinco recorridos end-to-end con las HU restantes,
no reabre ni duplica el cierre acotado de AARI-229 y no agrega tiempo de trabajo.

## Validación y pendientes

Pruebas nuevas: grafo real con módulos simulados, contrato HTTP sin sesión,
etapas seguras, datos extra prohibidos y resumen acotado; PostgreSQL real
con recovery en otro proceso, actividad/idempotencia, carreras, rollback
tras escribir el checkpoint, permisos por actor, expiración, prioridades,
sesiones vacías anteriores y coherencia del preflight.

Comandos desde backend:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_coordination.py tests/test_coordination_postgres.py
python -m pytest -q -p no:cacheprovider
python -m pip check
```

PostgreSQL usa AARI_TEST_POSTGRES_URL a una instancia local dedicada.
Cada fixture crea y elimina una base aari_pr26_<uuid>, con datos sintéticos.
Workers y trazas externas deshabilitados; no consume Gemini, SMTP, WhatsApp
ni Supabase real. El entorno anterior falló por distribución incompleta y
archivos de template1 ausentes; se detuvo sin repararlo. La validación continuó
con una distribución oficial nueva PostgreSQL 17.11 en loopback: 55427,
sin servicio del sistema. El ZIP es un artefacto local ignorado por Git.

Resultados del 11/10/2026:

- Primera pasada general sin PostgreSQL habilitado: **749 passed / 135 skipped**.
- Primera focalizada de HU21 real: **19 PostgreSQL aprobadas**.
- Tras ampliar permisos/carreras y recovery en otro proceso:
  **42 focalizadas aprobadas**, sin errores.
- Pasada final de toda la rama, incluidos controles adicionales de errores
  seguros y reapertura: **856 passed / 37 skipped**, 194,59 s, cero fallos.
  Hay 18 advertencias preexistentes del adaptador datetime SQLite de Python 3.12.
  Las omitidas son pruebas optativas de servicios/entornos específicos;
  no se presentan como validadas contra Supabase o canales reales.
- Frontend sin cambios: **316 passed en 35 archivos**, 191,91 s;
  lint y build correctos. Se reutilizó node_modules, sin reinstalar frontend.
- `pip check` sin conflictos, nueve archivos Python nuevos parseados,
  revisión del diff y `git diff --check` limpios. Búsqueda de patrones de
  credenciales sin coincidencias en los archivos nuevos.

Las pasadas no se suman: la final incluye las pruebas anteriores. El worker
quedó apagado y la instancia local se detuvo al terminar; se preserva el runtime
ignorado para reproducir la validación. La copia auxiliar gestionada se archivó
después de conservar el entorno virtual; código y docs quedan en .codex-hu21.
Notion se actualiza sobre el bloque existente del Hub, conservando lo de HU15;
la decisión completa permanece aquí por el límite conocido de creación de bloques.

No cerrar HU21 sólo por completar esta base. Pendientes:

1. Acordar e integrar los eventos de decisión, presupuesto, visita y
   cancelación de los módulos restantes; validar selección/intento vigente
   sin usar callbacks genéricos ni autoridad del cliente.
2. Ampliar los escenarios multi-turno con esas implementaciones reales y
   verificar los vencimientos específicos y recuperación end-to-end.
3. Revisión de Talía y confirmación de horas reales. La publicación de la base
   está autorizada; la migración y el QA compartido ya están validados.

Antes de usarla en producción también se debe acordar la retención de
checkpoints/eventos; esta base no borra evidencia histórica automáticamente.
