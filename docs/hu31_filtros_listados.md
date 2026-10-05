# HU31 — Filtros de listados y búsqueda visible

**Fecha:** 05/10/2026

**Rama:** `codex/AARI-332-home-administrador`

**Estado:** implementación validada; commit y push autorizados el 05/10/2026.

## Contexto y alcance aprobado

Durante la revisión del Home se propuso facilitar la búsqueda en los módulos
de propiedades, propietarios e inquilinos. La persona responsable aprobó
explícitamente incorporarlo **en la misma rama de HU31**, como excepción al
flujo habitual de una rama por tarea. No se cambia la estimación del Sprint,
no se crea otra historia ni se incorpora la rama de HU13.

La primera propuesta conservaba la búsqueda en la cabecera y agregaba criterios
estructurados. En la revisión se pidió que buscar una persona fuera más evidente
y que la flecha de “Filtros” no apareciera debajo del texto. Se aprobó añadir
un campo dentro del panel en propietarios e inquilinos y alinear la flecha a
la derecha. Se reutilizan componentes, tokens y reglas responsive de la skill
visual de AARI, sin modificar el botón compartido para los demás módulos.

## Comportamiento acordado

| Listado | Filtros |
|---|---|
| Propiedades | Tipo de inmueble, provincia, localidad, barrio, propietario y con/sin inquilino activo. |
| Propietarios | Búsqueda por nombre, DNI o email; con/sin inmuebles asociados. |
| Inquilinos | Búsqueda por nombre, DNI, email o propiedad; con/sin propiedad asignada, provincia y localidad de la propiedad actual. |

Los criterios se combinan con **AND**. La búsqueda libre conserva sus campos
existentes agrupados con OR entre paréntesis: coincidir por nombre no permite
ignorar los demás filtros. Tanto el total como las filas se filtran en el
backend **antes de paginar**, no sobre los diez registros ya visibles.

- Localidad y barrio requieren su nombre completo, sin distinguir mayúsculas;
  los extremos y espacios repetidos del criterio se normalizan. No se inventa
  un catálogo de localidades ni se aplica geolocalización.
- El propietario de una propiedad puede buscarse parcialmente por nombre,
  DNI o email. No se descarga todo el padrón para llenar un selector. En ese
  filtro, `%`, `_` y `!` se tratan como texto literal, no como comodines.
- Provincia usa el catálogo argentino existente. Tipo y estado usan los
  valores admitidos por los modelos; un valor inválido responde HTTP 422.
- La ubicación de un inquilino corresponde a su propiedad actual, no a su
  domicilio personal. “Sin propiedad” combinado con una ubicación no produce
  coincidencias; la interfaz lo explica.
- “Sin inquilino activo” indica ocupación, no disponibilidad comercial.
- Los contadores de inmuebles no duplican propietarios que tienen varias
  propiedades. Los valores booleanos `false` se envían explícitamente.

## Interfaz, sincronización y paginación

“Filtros” abre y cierra un panel compacto. La flecha permanece al lado del
texto y cambia de orientación al abrirlo. Los controles se reorganizan en
tres, dos o una columna según el ancho; en móvil se apilan las acciones y
los botones de paginación tienen una altura táctil mínima de 44 px.

En propietarios e inquilinos, el buscador del panel y el de la cabecera usan
**un único parámetro `search`**, no dos búsquedas independientes. El panel
mantiene un borrador hasta pulsar **Aplicar filtros** o Enter; la cabecera
actualiza la búsqueda al escribir y conserva los demás criterios. Se conserva
el espacio mientras se escribe un nombre compuesto; los extremos se normalizan
al consultar y al aplicar el panel.

- Aplicar búsqueda/filtros y limpiar vuelve a la primera página.
- Anterior/Siguiente conserva todos los criterios y se deshabilita en el
  extremo correspondiente. El total mostrado es el total de coincidencias.
- La URL conserva búsqueda, filtros y página al abrir un detalle y volver.
- Una página inválida se interpreta como la primera. Si se pide una página
  superior a la última, se consulta de nuevo la última válida, conservando los
  criterios y reemplazando la URL fuera de rango.
- Si la última página desaparece tras eliminar su único registro, se recupera
  la última válida. Cero coincidencias vuelve a la página uno y no muestra
  controles de navegación vacíos.
- Un fallo retira las filas anteriores. Las respuestas atrasadas de solicitudes
  canceladas no reemplazan una consulta más reciente.

## Componentes y dependencias

- `backend/app/schemas/list_filters.py`: criterios normalizados y tipados.
- Rutas, servicios y repositorios de los tres módulos: composición segura de
  consultas parametrizadas y total filtrado antes de LIMIT/OFFSET.
- `frontend/src/components/ui/ListFilterPanel.*`: panel, borrador y alineación.
- `frontend/src/hooks/useListFilters.js`: URL, búsqueda y recuperación de página.
- `frontend/src/services/listQuery.js` y API helpers: envío de criterios.
- Los tres listados, sus estilos y `frontend/src/layouts/AdminLayout.jsx`:
  composición, sincronización y estados de carga/vacío/error.

No se agregan migraciones, paquetes ni variables de entorno. Se mantienen las
rutas privadas de administración y los contratos de respuesta existentes.

## Pruebas y resultados

| Validación | Resultado |
|---|---|
| Backend completo: `python -m pytest -q -p no:cacheprovider` | **429 passed, 41 skipped**. Servicios externos deshabilitados. |
| Backend de filtros: `tests/test_admin_list_filters.py` | **37 pruebas**, incluidas en el total anterior. SQLite real en memoria y rutas HTTP protegidas. |
| PostgreSQL local: `tests/test_admin_list_filters_postgres.py` y `tests/test_admin_home_postgres.py` | **2 passed**. Bases aleatorias descartables y esquema de migraciones reales. |
| Frontend completo: `npm test -- --run --maxWorkers=2` | **191 passed** en 30 archivos. |
| Frontend de filtros: `src/features/adminListFilters.test.jsx` | **51 pruebas**, incluidas en el total anterior. |
| `npm run lint` y `npm run build` | Aprobados. |
| Chrome aislado con respuestas sintéticas | Tres módulos en 1440, 1024, 768, 390 y 320 px, sin desborde horizontal; alineación, teclado, búsqueda, paginación, errores y limpieza aprobados. |

Los casos automatizados incluyen combinaciones, paginación completa, totales,
páginas inválidas, recuperación de última página tras eliminación, búsqueda de
nombres compuestos, limpieza de borradores aún no aplicados, sincronización,
regreso desde detalle y respuestas atrasadas.
PostgreSQL comprueba además la conversión a texto del enum de tipo de inmueble;
no se utiliza `lower()` directamente sobre un enum.

Para reproducir las pruebas backend, usar el entorno aislado documentado en
[`hu31_home_administrador.md`](hu31_home_administrador.md), sin cargar `.env`.
Las dos pruebas PostgreSQL requieren `AARI_TEST_POSTGRES_URL` apuntando únicamente
a una instancia **local dedicada** con los roles locales sin login. El fixture
crea y elimina una base aleatoria por prueba; el caso de listados completa
también las migraciones 13 y 14 para las entregas de credenciales.

En este Windows se ejecutaron las entradas CLI equivalentes de Vitest, ESLint y
Vite con el runtime Node ya disponible. No se instalaron dependencias. Los
avisos preexistentes de Starlette/httpx y datetime de SQLite no impidieron las
pruebas. Capturas y script visual local en `backend/artifacts/hu31/`, ignorado
por Git, con datos ficticios.

## Límites y cierre

No se consumieron APIs externas, cuota, Storage ni SMTP; no se consultó ni
modificó Supabase para estas validaciones. La app local queda disponible para
revisión manual. Se registraron las 2h confirmadas por la persona responsable
en las subtareas de HU31, sin duplicarlas en la HU ni cambiar estados de cierre
o estimaciones originales. Reparto y worklogs en
[`hu31_home_administrador.md`](hu31_home_administrador.md).

Notion sigue pendiente de sincronización: el intento anterior de HU31 respondió
HTTP 403 por el límite de bloques gratuitos. No se declara publicada allí
esta ampliación; queda preservada en el repositorio según el acuerdo del Sprint.
HU31 aún requiere la conexión con HU13 después de su merge y revisión del PR.
Commit y push están autorizados; no se autoriza todavía el merge ni el cierre.
