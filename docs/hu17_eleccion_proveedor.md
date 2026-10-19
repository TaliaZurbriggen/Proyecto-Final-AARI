# HU17 — Elección del tipo de proveedor (AARI-191)

## Alcance y dependencia de revisión

Implementación local autorizada el 18/10/2026. Rama
`codex/AARI-191-eleccion-proveedor`, creada desde `origin/main` `02479b9` e
incorporando por avance rápido HU16 `eb5e0e9` (PR #35 aún en revisión).
No modifica la copia principal ni el trabajo de otras HU. La revisión del
incremento HU17 debe compararse con la rama HU16 mientras ésta no esté en main.
Publicación de commit, rama y PR autorizada el 18/10/2026, manteniendo revisión
separada de HU16. No se autoriza ni ejecuta merge por esta entrega.

Se eligió completar el encadenamiento solicitado en AARI-184 frente a declarar
HU16 cerrada con un marcador pendiente. La corrección está en esta rama
dependiente: el PR #35 por sí solo todavía no contiene el circuito HU17.
Las entregas y sus revisiones siguen separadas; no cerrar AARI-184 antes de que
se publique y revise la dependencia completa.

## Reglas y decisiones

- Ordinario: sólo el inquilino del reclamo, con unidad todavía asignada y cuenta
  activa, elige mientras está `Pendiente de respuesta del responsable`.
- Extraordinario: sólo el propietario actual de la unidad, después de autorizar
  (`Autorizado`). Rechazo, expensa y autorización pendiente no abren esta etapa.
- La identidad y el rol provienen de la sesión y se revalidan en PostgreSQL,
  incluyendo primer ingreso, perfil, titularidad/asignación, etapa y plazo.
- La etapa HU17 tiene fechas propias: recordatorio a las 48 h y vencimiento a
  las 72 h. En extraordinarios comienza al autorizar, no al pedir autorización.
  No se reutiliza el tiempo consumido en HU16.
- La decisión explícita pasa por un grafo LangGraph determinista, sin LLM ni
  llamadas externas, y guarda la salida dentro de la transacción de negocio.

| Elección | Estado confirmado | Próximo módulo (no implementado aquí) |
| --- | --- | --- |
| Fidelizado | Pendiente de asignación | HU19: solicitar presupuestos; candidatos obtenidos por HU15 |
| Propio | Pendiente de datos de proveedor propio | HU18: registrar los datos de contacto |

El estado nuevo evita afirmar `Derivado a proveedor externo` antes de registrar
el contacto en HU18. Elegir fidelizado tampoco selecciona, contrata ni confirma
disponibilidad de un proveedor, ni envía pedidos de presupuesto.
HU18/HU19 pertenecen a otra entrega: no se implementan formularios de contacto,
presupuestos, WhatsApp ni coordinación de visitas. La orquestación completa de
HU21 continúa en AARI-345; este subgrafo no acredita esa integración ni utiliza
el código todavía no fusionado del PR #34.

## Acceso y encadenamiento

- Inquilino: **Mis reclamos → detalle ordinario → Elegir tipo de proveedor**.
- Propietario: **Autorizaciones → revisar gasto → Autorizar intervención**.
  Al recibir la autorización confirmada, navega automáticamente a la elección.
- Rutas: `/{inquilino|propietario}/reclamos/{uuid}/tipo-proveedor`.
- Reabrir una autorización ya confirmada ofrece un enlace a la elección.
- Las dos tarjetas reutilizan Button, AlertMessage, StatusBadge, PageContainer,
  PageHeading, tokens e iconos AARI; en móvil quedan apiladas. Incluyen carga,
  acceso denegado, error de red, guardado, conflicto, vencimiento y decisión ya
  persistida. No se muestran botones de HU18/HU19 que todavía no funcionan.

## API y persistencia

`GET /reclamos/{uuid}/tipo-proveedor` consulta sin escribir: devuelve etapa,
plazo, versión, permiso efectivo y decisión anterior si existe.

`POST /reclamos/{uuid}/tipo-proveedor` recibe exclusivamente:

```json
{
  "request_id": "UUID nuevo por intento de decisión",
  "solicitud_id": "UUID de la etapa devuelto por GET",
  "expected_updated_at": "fecha ISO-8601 con zona devuelta por GET",
  "tipo_proveedor": "fidelizado o propio"
}
```

Identidad adicional, opciones desconocidas y fechas sin zona: 422. Sesión o rol
no habilitados: 401/403. Reclamo ajeno o etapa no existente: 404 sin exponer
datos. Elección ya tomada, etapa/versión obsoleta o plazo agotado: 409.

El servidor bloquea cuenta → perfil → unidad → reclamo → solicitud, revalida
antes de escribir y usa la hora de PostgreSQL después de obtener el bloqueo.
Transición, historial, auditoría y cancelación de avisos obsoletos confirman o
revierten juntos. Un replay del mismo UUID/payload/usuario devuelve el resultado
original; cambiar elección, etapa o versión con ese UUID no está permitido.
El navegador conserva el intento ante una respuesta de red perdida y bloquea
la opción opuesta hasta resolverla. Tras un conflicto vuelve a consultar.

`reclamo_elecciones_proveedor` conserva etapa, solicitud HU12 de origen, actor,
plazos, elección, usuario/nombre al decidir, timestamp, UUID, versión y vínculo
al historial. La unicidad por reclamo/solicitud de responsable evita duplicar
la etapa. No se reabre una etapa vencida o decidida al repetir un evento.
Una futura reelección corresponde a HU24, no a sobreescribir esta auditoría.

## Jobs y avisos

Se usa el worker/outbox existentes, sin otro daemon:

1. Los triggers privados abren la etapa atómicamente al clasificar ordinario o
   autorizar extraordinario. DDL no cambia filas históricas.
2. El worker descubre casos previos elegibles usando la fecha original de
   clasificación o la auditoría de autorización, nunca la hora del descubrimiento.
   GET no inicializa ni prorroga etapas.
3. A las 48 h se encola un recordatorio con vínculo autenticado y vencimiento.
4. A las 72 h sin elección: `Pendiente de respuesta - vencido`, historial y aviso
   al operador asignado, con fallback operativo existente. Si no hay ninguna
   cuenta operativa, igualmente persiste el estado vencido.
5. La etapa HU17 reemplaza los plazos de HU12 para ese ciclo, evitando avisos
   duplicados. Autorizaciones todavía pendientes conservan el job HU16.
6. Elecciones resueltas/vencidas invalidan recordatorios pendientes o en proceso.
   Un resultado de envío tardío no puede reactivarlos. Un mensaje ya aceptado por
   SMTP/WhatsApp no puede retirarse; encolar no acredita entrega.

El job detecta la tabla antes de activarse para no romper los jobs previos
durante un despliegue gradual. Esto no sustituye aplicar la migración antes de
exponer las rutas HU17. Los canales se reutilizan con sus permisos existentes;
las pruebas sólo reservan/verifican avisos o usan dobles, sin enviarlos.

## Migración aplicada y despliegue controlado

Archivo generado con Supabase CLI oficial 2.81.3:
`backend/migrations/20261018235315_hu17_eleccion_proveedor.sql`.
Aplicada con autorización el **18/10/2026 (Argentina)** al Supabase AARI de
desarrollo, PostgreSQL 17.6. Historial remoto asignado por el conector:
`20261019003825_hu17_eleccion_proveedor` (19/10 UTC). El archivo local conserva
`20261018235315`; no renombrarlo ni repetirlo por integrante, pull o merge.
Requiere HU16, HU12 y outbox HU10/HU14. No editar ni volver a aplicar las anteriores.

Agrega la tabla de etapa/auditoría privada con RLS, revocaciones de
PUBLIC/anon/authenticated, CHECK y FK indexadas; referencia compuesta desde el
outbox; eventos de recordatorio/vencimiento; el estado pendiente de contacto en
reclamos y notificaciones; dos triggers SECURITY INVOKER con search_path vacío.
Extiende sólo el mensaje del nuevo estado en la función vigente, con guarda de
plantilla que aborta si difiere de la base esperada; conserva ACL y demás lógica.
Límites transaccionales: bloqueo 5 s, ejecución 30 s. No borra registros,
reinicia secuencias, crea usuarios ni encola mensajes retroactivos en el DDL.

Preflight y verificación posterior: 39 tablas anteriores / 58 filas con conteos
idénticos; RLS, ACL, políticas y numeración anteriores conservados. Guardas de
conteos y plantilla antes/después en la misma transacción; la función conserva
sus permisos. Nueva tabla vacía, sin avisos vinculados: tres FK y cinco CHECK,
PK/tres unicidades y nueve índices incluyendo el del outbox, todos válidos.
Dos triggers habilitados; ambas funciones SECURITY INVOKER con search_path vacío.
Sin permisos de tabla, columna o ejecución para anon/authenticated/PUBLIC.
No se escribieron elecciones, solicitudes, estados, usuarios ni mensajes.

La lectura amplia de huellas de contenido privado fue rechazada por el control
de privacidad; no se intentó obtenerlas por otro medio. Se usó la alternativa
de conteos y metadatos sin extraer contenido ni huellas privadas. Esta validación
no afirma igualdad de contenido fila por fila, copia de respaldo de datos ni
una prueba funcional de escritura en Supabase.

Asesores: sin nuevas advertencias ni FK nuevas sin índice; permanecen las 16 FK
previas sin índice. Sólo se agregan INFO por tabla privada RLS sin políticas e
índices aún sin uso. Advertencias previas fuera de alcance:

- [search_path mutable de set_updated_at](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable).
- [rls_auto_enable ejecutable por anon](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable).
- [rls_auto_enable ejecutable por authenticated](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable).

La aplicación local estaba detenida, sin procesos en 8000/5173, y el preflight
no detectó escrituras de negocio activas. No se activaron workers ni canales.
Confirmar por separado cuándo reactivar el worker: puede descubrir y vencer
solicitudes históricas ya agotadas y encolar sus avisos reales.
No requiere claves, dependencias ni campos nuevos en `.env`.

## Validación

Pruebas en PostgreSQL 17.11 local descartable y dobles HTTP/UI, sin Supabase,
SMTP, WhatsApp, Storage ni cuota de modelos. Identidades/contactos ficticios.

Comandos de referencia desde `backend/`, con workers/servicios externos apagados:

```powershell
python -m pytest tests/test_provider_choices.py tests/test_provider_choices_postgres.py -q
python -m pytest -q --ignore=tests/test_provider_candidates_volume_postgres.py --basetemp=RUTA_ABSOLUTA_NUEVA_DE_QA
python -m pip check
```

`AARI_TEST_POSTGRES_URL` sólo puede apuntar al clúster local dedicado: las
fixtures verifican loopback y crean/eliminan una base sintética por caso.
No apuntar a Supabase. `--basetemp` debe ser una ruta absoluta nueva y descartable:
pytest elimina su contenido al comenzar. Nunca usar una carpeta con datos.

Desde `frontend/`: `npm test`, `npm run lint`, `npm run build`.

Resultados del 18/10/2026:

- Regresión backend, salvo volumen HU15 sin cambios: **980 aprobadas / 51
  omitidas**, 309,26 s; PostgreSQL 17.11 local incluido. Las 18 advertencias
  previas de adaptación datetime de SQLite permanecen, sin errores.
- Comprobación adicional de PostgreSQL HU17 y estados: **31 aprobadas**,
  69,42 s. Incluye seis casos agregados después de iniciar la regresión y casos
  repetidos: no sumar 31 al total ni afirmar una sola corrida de 1.011.
- Las 46 variantes nuevas HU17 cubren reglas/grafo/API (21) y PostgreSQL (25):
  ambas elecciones y actores, HU16→HU17, rechazo/expensa excluidos, GET sin
  escrituras, perfil/asignación/cuenta, versiones/etapas, replay, carrera de
  decisiones, rollback, recuperación de fechas previas, plazos, recordatorios
  concurrentes y cancelación de avisos tardíos.
- Frontend completo: **350 aprobadas / 38 archivos**, 72,10 s; nueve casos
  nuevos HU17 y regresiones HU16, incluido autorizar→cargar elección→guardar.
  `npm run lint` y `npm run build` correctos (build final 1,96 s).
- `pip check`, diff/formato y revisión de patrones de secretos en líneas nuevas
  y archivos nuevos correctos. Sin cambios de dependencias o `.env`.
- Cero bases ficticias remanentes; app de QA y PostgreSQL dedicado detenidos.

Repetición previa a publicar, después de aplicar el esquema compartido:
`pytest` focalizado HU17/HU16/estados/plantillas, **48 aprobadas** (0,75 s,
mocks/SQLite); UI HU17/HU16 **18 aprobadas** (10,90 s); lint, build (1,53 s) y
pip check correctos. Son repeticiones, no se suman a las suites anteriores.
No se volvió a ejecutar PostgreSQL local ni pruebas compartidas de escritura
por esta publicación; sólo preflight, DDL y lecturas de esquema/conteos.

La primera regresión se repitió: un test estructural esperaba todos los estados
en HU10 original (ahora valida también la incremental sin reescribir historia)
y 54 preparaciones fallaron al crear la carpeta temporal relativa. Ruta absoluta
nueva comprobada, repetición completa exitosa. La primera pasada HU17 encontró
el estado del aviso sin completar, corregido y repetido; la primera pasada UI
tuvo un doble de autorización incompleto, corregido sin errores en la corrida
completa. No se contabilizan esas pasadas fallidas como validaciones aprobadas.

Verificación visual local: aplicación y repositorios reales con PostgreSQL,
identidad inyectada ficticia y canales deshabilitados, en puertos separados
8002/5175. Autorizar abrió HU17 automáticamente; elección propia persistió el
estado pendiente de datos, sin derivación. Escritorio 1280 px y móvil 390 px,
tarjetas apiladas sin scroll horizontal; orden de teclado y foco compartido.
No acredita login real, entrega de correos ni despliegue compartido.

## Estado de gestión

HU17 y subtareas AARI-192..198 En curso. AARI-184 no se marca Listo antes de
revisar/publicar la dependencia completa. Sin worklogs nuevos: las horas reales
se registran únicamente con una duración confirmada por el responsable.
Notion documenta la decisión y dependencia; Jira mantiene avance, no aprobación
implícita de merge/cierre. Migración compartida y publicación autorizadas el
18/10/2026; la migración ya está aplicada y validada según la sección anterior.
Rama/commit/PR y estado de revisión se registran en Jira y Notion al publicar.
Prueba funcional compartida de escritura y reactivación de canales no realizadas.
