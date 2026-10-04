# HU11 — Historial de reclamos de una propiedad

Jira: [AARI-125](https://taliazurbriggen.atlassian.net/browse/AARI-125).
Implementación local del 02/10/2026, rama
`codex/AARI-125-historial-reclamos-propiedad`, desde `main` actualizado
(`053a712`, merge del PR #26). HU y subtareas AARI-126 a AARI-134 en curso;
pendientes revisión funcional, autorización de commit y PR. No se registró
tiempo de HU11: se requiere confirmación del tiempo real por parte de Tobías.

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
- Suite completa: **342 aprobadas, 39 omitidas**, sin fallos. Las omisiones
  corresponden a PostgreSQL local y servicios externos optativos. Se conservan
  18 advertencias de deprecación del adaptador datetime de SQLite.

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
- Navegador: componentes reales con respuestas HTTP simuladas, escritorio y
  móvil de 390 px; navegación con Tab/Enter y sin desborde horizontal de página.
  Esta revisión visual no equivale a probar una cuenta real contra Supabase.

## Validaciones pendientes y entrega

La prueba optativa `tests/test_property_claims_postgres.py` está preparada
para ejecutar SQL sobre PostgreSQL local con migraciones existentes y datos
sintéticos. Reutiliza la fixture aislada de HU12, que restringe la URL a
loopback y crea/elimina una base `aari_pr26_<uuid>` por caso. Se activa mediante
`AARI_TEST_POSTGRES_URL` apuntando a una instancia local dedicada; no usar la
URL del Supabase compartido. Ejecutar:

```powershell
python -m pytest tests/test_property_claims_postgres.py -q
```

No pudo validarse: la instalación temporal de PostgreSQL disponible está
incompleta y no inicia. El intento devolvió conexión rechazada; en la suite
completa este caso quedó omitido. No se ejecutaron consultas en Supabase,
llamadas a Gemini ni envíos SMTP. Pendiente prueba funcional con las cuentas
del entorno y validación PostgreSQL real antes del cierre definitivo.

El 02/10 se intentó registrar la decisión en la página ADR de Notion. Notion
rechazó la escritura con `entitlement_required` porque el espacio agotó sus
bloques gratuitos, sin cambios parciales. Esta documentación conserva la
decisión y su evidencia hasta que el espacio permita escrituras.

No hay commit ni PR de HU11 todavía. La revisión y el tiempo real se confirman
con Tobías antes de publicar o cerrar la HU y sus subtareas.
