# HU31 — Filtros de listados y búsqueda visible

**Fecha:** 05/10/2026

**Rama:** `codex/AARI-332-home-administrador`

**Estado:** entrega inicial publicada con autorización; corrección de revisión
del 08/10/2026 validada, commit/push autorizados y nueva revisión pendiente.

## Contexto y alcance aprobado

Durante la revisión del Home se propuso facilitar la búsqueda en los módulos
de propiedades, propietarios e inquilinos. La persona responsable aprobó
explícitamente incorporarlo **en la misma rama de HU31**, como excepción al
flujo habitual de una rama por tarea. No se cambia la estimación del Sprint,
no se crea otra historia ni se incorpora la rama de HU13 en esa entrega inicial.
El 07/10 esta rama se actualizó desde main, que ya contiene HU13/HU30/HU14,
para completar la conexión aprobada del Home sin alterar los filtros.

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

## Pruebas y resultados de la entrega inicial — 05/10/2026

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
modificó Supabase para estas validaciones. Se revisó una app local aislada
con datos ficticios. Se registraron las 2h confirmadas por la persona responsable
en las subtareas de HU31, sin duplicarlas en la HU ni cambiar estados de cierre
o estimaciones originales. Reparto y worklogs en
[`hu31_home_administrador.md`](hu31_home_administrador.md).

Notion sigue pendiente de sincronización: el intento anterior de HU31 respondió
HTTP 403 por el límite de bloques gratuitos. No se declara publicada allí
esta ampliación; queda preservada en el repositorio según el acuerdo del Sprint.
La conexión con HU13 se completó el 07/10 después del rebase sobre main
`69d0ec6`. La revalidación final conservó todos los filtros y la paginación:
**808 backend aprobadas / 37 omitidas**, **235 frontend aprobadas**, lint/build
correctos. Se repitió Chrome en los tres listados a 1440, 1024, 768, 390 y
320 px: alineación, área táctil, búsqueda sincronizada, conservación de filtros
al cambiar de página, teclado, error sin resultados viejos y limpieza aprobados.
Comandos, recorrido con HU13 y límites en
[`hu31_home_administrador.md`](hu31_home_administrador.md).

La entrega inicial se publicó con autorización el 05/10. La persona responsable
autorizó el commit/push de la continuación el 07/10 después de aprobar la vista.
La revisión final repitió **808 backend aprobadas / 37 omitidas**,
**238 frontend aprobadas**, lint/build y el recorrido integrado en Chrome aislado.
Se registraron **1h 15m adicionales**: la HU acumula **3h 15m**, solo en sus
subtareas. Registro y worklogs en el informe del Home. Quedan revisión y PR;
no se autoriza todavía el merge ni el cierre de HU31.

## Corrección de retorno desde detalle — 08/10/2026

### Hallazgo y decisión aprobada

La revisión del PR #31 detectó que los enlaces reales «Volver al listado»
apuntaban a la raíz del módulo y perdían búsqueda, filtros y página. La prueba
anterior sustituyó el detalle por una pantalla simulada que volvía mediante
el historial (`navigate(-1)`); por eso sus resultados históricos no verificaban
el enlace real. Se conserva esa evidencia histórica y se explicita su límite.

La propuesta aprobada conserva el contexto en un parámetro `returnTo` de la
URL del detalle, codificado con `URLSearchParams`. No se depende del historial
del navegador, de almacenamiento local ni únicamente del estado de React:
el enlace sigue siendo útil al recargar o abrirlo en otra pestaña.

El retorno se valida contra el listado exacto del mismo módulo y su query.
Destinos externos, otros módulos, fragmentos, barras invertidas, caracteres
de control o parámetros `returnTo` duplicados se rechazan. Si falta un retorno
válido, se vuelve a `/propietarios`, `/propiedades` o `/inquilinos`, según la
pantalla. Los caracteres de la búsqueda no se decodifican dos veces.

### Implementación

- `frontend/src/services/listNavigation.js`: construcción del enlace al detalle
  y resolución del retorno seguro, compartidas por los tres módulos.
- Los listados de propietarios, propiedades e inquilinos añaden el contexto
  tanto al enlace de nombre/dirección como a la acción de ver detalle.
- Los tres detalles usan ese destino en «Volver al listado», también durante
  la carga o si el registro no existe. La eliminación desde el detalle vuelve
  al mismo contexto, manteniendo el aviso de éxito y la recuperación de una
  última página que haya desaparecido.
- `frontend/src/features/adminListFilters.test.jsx` utiliza los componentes
  reales de listado y detalle, con APIs simuladas; se eliminó el detalle falso.
- `frontend/src/services/listNavigation.test.js` cubre codificación y rechazo
  de destinos no válidos.

Se mantuvieron los enlaces, estilos, componentes y comportamiento responsive
existentes siguiendo la skill `aari-frontend`. No cambian CSS, backend,
dependencias, migraciones ni configuración. No se amplía el alcance a los
formularios de alta/edición ni a enlaces entre módulos distintos.

### Validaciones y resultados

Antes de corregir las pantallas se ejecutaron las nuevas pruebas que abren el
detalle real: **6 fallaron** como se esperaba, reproduciendo el hallazgo en
ambos enlaces de los tres módulos. Después de la corrección:

| Validación | Resultado |
|---|---|
| `node node_modules/vitest/vitest.mjs run src/features/adminListFilters.test.jsx src/services/listNavigation.test.js --maxWorkers=1 --reporter=dot` | **129 passed**: 75 pruebas de listados/detalles y 54 de retorno seguro. |
| `node node_modules/vitest/vitest.mjs run --maxWorkers=2 --reporter=dot` | **316 passed**, 35 archivos, sin fallos. |
| `node node_modules/eslint/bin/eslint.js .` | Aprobado. |
| `node node_modules/vite/bin/vite.js build` | Aprobado. |
| Chrome aislado, datos ficticios, 1440/390/320 px | **9 recorridos aprobados**, los tres módulos en cada ancho. |
| `git diff --check` y revisión del diff | Sin errores de formato; sin claves ni datos personales añadidos. |

Los comandos frontend se ejecutan desde `frontend/`, usando Node disponible
en Windows. Son las entradas CLI equivalentes a los scripts del proyecto.
La suite completa se ejecutó después del último ajuste del helper.

Las pruebas comprueban búsqueda, filtros y página tanto al volver como al
acceder directamente mediante la URL del detalle; incluyen caracteres
especiales, retorno ausente/inválido, error 404 y recuperación de la última
página tras una eliminación o un cambio de total mientras se ve el detalle.

En Chrome se verificaron navegación por teclado, foco visible, enlace real de
retorno, recarga, pestaña nueva sin historial, fallback seguro, criterios
enviados a la API simulada y ausencia de desborde horizontal. Se verificó que
la fuente Inter se cargara correctamente y que no hubiera errores HTTP ni
JavaScript. Capturas y script local: `backend/artifacts/hu31/`, ignorado por Git.
La prueba visual se ejecutó en un servidor temporal aislado, sin alterar los
procesos de la app del usuario.

### Límites y estado de entrega

No se repitieron las pruebas backend porque esta corrección no lo modifica.
No se consultó Supabase, Gemini, Storage ni SMTP; las APIs del navegador fueron
simuladas. No se instalaron paquetes.

La corrección permanece en la rama existente de HU31, sin rebase ni cambios
en trabajo ajeno. Después de validar el resultado, la persona responsable
autorizó el commit/push el 08/10. La publicación se registra mediante un
comentario en AARI-332 con rama, commit y validaciones, según `AGENTS.md`.
No se autorizó el merge, el cierre de la HU ni nuevos registros de tiempo.
El PR #31 requiere una nueva revisión antes de aprobarse o integrarse.

Notion continúa pendiente por el límite gratuito de bloques (HTTP 403
`block_limit_reached` registrado previamente). No se declara sincronizada allí
esta corrección; la documentación queda preservada en el repositorio.
