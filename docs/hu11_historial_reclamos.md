# HU11 — Historial de reclamos de una propiedad

Jira: [AARI-125](https://taliazurbriggen.atlassian.net/browse/AARI-125).
Implementación del 02/10/2026, validada y publicada el 04/10/2026, rama
`codex/AARI-125-historial-reclamos-propiedad`, desde `main` actualizado
(`053a712`, merge del PR #26). HU y subtareas AARI-126 a AARI-134 en curso;
pendiente revisión de Talía en el [PR #27](https://github.com/TaliaZurbriggen/Proyecto-Final-AARI/pull/27).
Commit inicial `17e67ae`. PostgreSQL real y flujo funcional aprobados.
Tiempo real confirmado y registrado en Jira: **40 minutos**; no se agregó
tiempo por la validación ni se cerraron la HU o sus subtareas.

## Alcance y acceso

- Administración: todos los reclamos de la propiedad seleccionada.
- Inquilino: únicamente los reclamos presentados por su propia identidad,
  incluyendo los de propiedades anteriores. Una mudanza no elimina ese acceso.
- Propietario y operador no acceden a estas rutas. Sus flujos corresponden a
  otras historias; esta HU no cambia estados ni crea notificaciones.
- Propiedad ajena al inquilino: `403`, sin revelar si existe. Reclamo ajeno
  dentro de una propiedad accesible: `404`. Administración recibe `404` ante
  una propiedad inexistente. Sin sesión: `401`; primer ingreso pendiente: `403`.

Los permisos se aplican en FastAPI y en las consultas del repositorio, no solo
en React. El identificador del inquilino y el usuario salen de la sesión;
no se aceptan desde filtros. Listado, total y detalle usan el mismo alcance.
El historial devuelve dirección y unidad, sin contactos ni notas internas.

## API y filtros

`GET /propiedades/{id}/reclamos` devuelve `propiedad`, `items`, `total`, `page`,
`page_size` y `total_pages`. Además expone `X-Total-Count` mediante CORS.

| Parámetro | Comportamiento |
| --- | --- |
| `page` | Desde 1; tamaño fijo de 20, sin parámetro libre de tamaño. |
| `estado` | Estado vigente del reclamo, validado contra el contrato existente. |
| `tipo_gasto` | `ordinario`, `extraordinario`, `expensa` o `sin_clasificar` para `NULL`. |
| `fecha_desde` | Desde el comienzo del día de ingreso, inclusive. |
| `fecha_hasta` | Hasta el final del día de ingreso, inclusive. |

Los filtros se combinan con AND. Los límites de días usan
`America/Argentina/Buenos_Aires`, convirtiéndolos a UTC para comparar
`creado_en`: inicio inclusive y medianoche siguiente exclusiva. Un rango
invertido o un filtro inválido responde `422`. La fecha hasta no puede ser
31/12/9999, porque no se puede calcular el día siguiente.

Orden: fecha de ingreso descendente, con número descendente como desempate
estable. Una página fuera del rango devuelve una lista vacía, conservando el
total; la interfaz permite volver a la primera página.

`GET /propiedades/{id}/reclamos/{reclamo_id}` devuelve la descripción completa,
estado, urgencia, tipo de gasto, propiedad, fechas e historial de transiciones
(estado previo/nuevo, fecha y origen). La interfaz muestra los cambios más
recientes primero. No se agregan acciones operativas, adjuntos ni información
privada del agente a esta vista.

## Interfaz y flujo de prueba manual

Con backend y frontend iniciados como indica el README, usar `localhost` para
ambos, sin mezclarlo con `127.0.0.1`.

### Administración

1. Iniciar sesión con una cuenta administrativa existente.
2. Entrar a **Propiedades**, abrir una ficha y elegir **Ver historial de reclamos**.
3. Comprobar número, descripción resumida, estado, tipo de gasto y fecha.
4. Combinar filtros por estado, gasto y fechas; comprobar el total. Los cambios
   consultan la API sin recargar toda la página y reinician la paginación.
5. Probar un día específico poniendo la misma fecha desde/hasta. Probar un
   rango invertido: debe aparecer validación, sin solicitar resultados.
6. Con más de 20 coincidencias, avanzar y retroceder con el paginador.
7. Abrir el número de un reclamo y revisar descripción completa y transiciones.
   Volver al historial: los filtros y la página deben conservarse en la URL.
8. Limpiar filtros; probar una combinación sin coincidencias y una propiedad
   sin reclamos. Deben mostrarse estados vacíos explicativos.

### Inquilino y límites de acceso

1. Iniciar sesión con una cuenta de inquilino existente que tenga reclamos.
2. Entrar a **Mis reclamos** y elegir **Historial de [propiedad]**.
3. Verificar el aviso de alcance propio y que no aparezcan reclamos de otros
   inquilinos. Revisar filtros, total y detalle.
4. Usar dos cuentas sintéticas de inquilino vinculadas a la misma propiedad:
   cada una debe ver solamente sus reclamos. La API debe rechazar un detalle
   ajeno aun cuando se copie su UUID.
5. La consulta de una propiedad sin vínculo actual ni reclamos propios debe
   responder `403`. No modificar usuarios reales para preparar esta prueba.

En móvil, los filtros pasan a una columna y las filas muestran sus etiquetas
junto a los valores. Se reutilizan tokens, badges, campos, botones y layouts
de AARI. Hay estados de carga, error, vacío y foco. Las respuestas tardías de
una consulta anterior se descartan y las solicitudes se abortan al salir.

## Decisión técnica: lectura aislada, sin migración

Se reutilizan `propiedades`, `inquilinos`, `reclamos` y
`reclamo_historial_estados`, con los índices ya existentes sobre propiedad,
inquilino, estado y tipo de gasto. No hay variables `.env` nuevas, dependencias
nuevas ni migración por ejecutar.

Se descartó filtrar únicamente en el frontend porque permitiría eludir
permisos. La ruta de historial se registra separada del CRUD administrativo,
para no abrir dicho CRUD al inquilino. Se descartó limitar el acceso solo a la
propiedad actual porque ocultaría reclamos propios tras una mudanza. La
combinación de identidad y reclamos propios conserva trazabilidad sin abrir
el historial de otras personas.

Los componentes principales son `PropertyClaimsHistoryPage`,
`PropertyClaimDetailPage`, el hook `useHistoryResource` y el módulo backend
`property_claims` en API, servicio, esquema y repositorio. Se agregan accesos
desde la ficha de propiedad y desde Mis reclamos; se conserva el seguimiento
existente de HU10.

## Validación ejecutada

Desde `backend/`, con los flags de pruebas externas desactivados:

```powershell
python -m pytest tests/test_property_claims.py -q
python -m pytest -q --tb=short
```

- Focalizadas HU11: **20 aprobadas** con FastAPI y SQL real sobre SQLite aislado.
  Cubren roles, identidad, reclamos propios/ajenos, historial tras mudanza,
  filtros combinados, rango completo con límites exactos, orden estable,
  paginación, totales y cabecera CORS.
- Suite completa inicial: **342 aprobadas, 39 omitidas**, sin fallos.
- Suite completa con PostgreSQL 17.11 local habilitado: **355 aprobadas,
  26 omitidas**, sin fallos, en 50,11 segundos. Las omisiones restantes
  corresponden a integraciones optativas, no a la prueba PostgreSQL de HU11.
  Se conservan 18 advertencias de deprecación del adaptador datetime de SQLite.

Desde `frontend/`:

```powershell
npm run lint
npm run test -- --run
npm run build
```

- Lint y build: **aprobados**.
- Suite completa: **110 pruebas aprobadas en 25 archivos**; 10 casos nuevos
  cubren tabla, filtros, paginación, detalle, retorno con filtros, vacío,
  rango inválido, permisos, páginas fuera de rango y respuestas tardías.
- Revisión visual inicial: componentes reales con respuestas HTTP simuladas, escritorio y
  móvil de 390 px; navegación con Tab/Enter y sin desborde horizontal de página.
  Esta revisión visual no equivale a probar una cuenta real contra Supabase.

## PostgreSQL real y prueba funcional — 04/10/2026

La prueba optativa `tests/test_property_claims_postgres.py` está preparada
para ejecutar SQL sobre PostgreSQL local con migraciones existentes y datos
sintéticos. Reutiliza la fixture aislada de HU12, que restringe la URL a
loopback y crea/elimina una base `aari_pr26_<uuid>` por caso. Se activa mediante
`AARI_TEST_POSTGRES_URL` apuntando a una instancia local dedicada; no usar la
URL del Supabase compartido. Ejecutar:

```powershell
# Ejemplo para la instancia local dedicada utilizada en esta validación.
$env:AARI_TEST_POSTGRES_URL = 'postgresql://aari_test@127.0.0.1:55426/postgres'
$env:DATABASE_URL = $env:AARI_TEST_POSTGRES_URL
python -m pytest tests/test_property_claims_postgres.py -q --tb=short
python -m pytest -q --tb=short
```

Resultado focalizado: **1 aprobada** en 3,51 segundos. El caso comprueba
paginación 20/5, tipos enum de PostgreSQL, fechas `timestamptz` con ambos límites
exactos del día argentino, alcance propio, detalle ajeno rechazado, historial
registrado por el trigger y acceso histórico después de quitar la asignación.

La instalación temporal anterior estaba incompleta (`libintl-9.dll` faltante).
Se usó el paquete completo portable de PostgreSQL **17.11**, sin instalar
servicios de Windows, cambiar PATH ni modificar la instalación del proyecto.
Solo escucha en loopback, en el puerto dedicado **55426**. Las migraciones
existentes se aplicaron exclusivamente a bases descartables locales; HU11
no introduce una migración nueva.

Se probó además la aplicación real, sin simular respuestas de API, con
frontend en `localhost:5181` y backend en `localhost:8001`, sobre otra base
descartable. Se cargaron dos propiedades y 25 reclamos ficticios, 22 de un
inquilino y 3 de otro, con cuentas de prueba y credenciales aleatorias locales.
Las migraciones existentes 13, 14 y 20 completaron autenticación y contratos
en esa base de QA, sin ejecutar seeds de contactos reales.

Comprobaciones funcionales realizadas:

- Login real con `crypt`, cookie HttpOnly, `/auth/me` y logout.
- Administración: Propiedades → ficha → Ver historial de reclamos; total 25,
  páginas de 20 y 5. Filtros Resuelto + Ordinario + 01/10/2026: total 22,
  páginas de 20 y 2 (excluye el reclamo En proceso y ambos límites externos).
- Detalle, descripción, cronología y vuelta conservando los cuatro filtros
  y la página 2. Rango invertido bloqueado en interfaz; API responde `422`.
- Limpieza de filtros, combinación sin coincidencias y propiedad sin reclamos.
- Inquilino: Mis reclamos → Historial de propiedad anterior; total 22, páginas
  de 20 y 2, sin los tres reclamos de la otra cuenta. Detalle propio con
  cronología En proceso → Resuelto, del cambio más reciente al inicial.
- API con segunda cuenta: total 3, no 25. Reclamo ajeno `404`, propiedad sin
  vínculo `403`, operador/propietario `403`, falta de sesión `401`. La interfaz
  presenta errores y no muestra datos ajenos.
- Escritorio y móvil de 390 × 844: tabla adaptada con etiquetas, filtros en
  una columna y detalle sin desborde horizontal de página. Se restauró el
  tamaño normal del navegador al terminar.

No se ejecutaron consultas en Supabase, llamadas a Gemini ni envíos SMTP.
El worker de notificaciones estuvo desactivado durante QA. Las configuraciones
de prueba se pasaron al proceso, sin editar los `.env` del proyecto. La base
de QA y sus cuentas se eliminaron al terminar; no son cuentas disponibles para
el entorno compartido.

## Entrega y pendientes

El 02/10 se intentó registrar la decisión en la página ADR de Notion. Notion
rechazó la escritura con `entitlement_required` porque el espacio agotó sus
bloques gratuitos, sin cambios parciales. Esta documentación conserva la
decisión y su evidencia hasta que el espacio permita escrituras.

El PR #27 se publicó inicialmente en borrador y se actualiza con la evidencia
de PostgreSQL real y recorrido funcional antes de solicitar revisión. No se
fusiona automáticamente: resta revisión/aprobación de Talía e indicación de
cierre de Jira. La réplica de la decisión en Notion sigue pendiente por el
límite de bloques, no por falta de documentación en el repositorio.
