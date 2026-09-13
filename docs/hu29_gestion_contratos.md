# HU29 / AARI-318 — Gestión de contratos de alquiler

## Estado al 13/09/2026

Implementación en `feat/AARI-318-gestion-contratos`, creada desde
`origin/main` (`1cc1530`). Jira: HU29 y subtareas en curso.
**Entrega para Pull Request autorizada el 13/09/2026**, después de la revisión
visual del equipo y los ajustes solicitados. Storage real validado. La persona
responsable creará el PR; la HU permanece en curso hasta revisión y merge.

La migración 20 se aplicó el **13/09/2026** al Supabase compartido de desarrollo,
mediante `scripts/check_contracts_postgres.py --mode apply`.
Antes se ejecutó la misma migración en un esquema temporal y se verificó su
rollback. La aplicación real fue aditiva: no creó cuentas ni contratos y no
modificó filas de los módulos anteriores. No repetirla por integrante o por pull.

La documentación se conserva en el repositorio según la planificación del
Sprint 3 mientras Notion esté bloqueado por su límite de bloques; queda pendiente
trasladar allí el resumen definitivo. No se informó una publicación en Notion.

## Decisiones acordadas

| Tema | Decisión y motivo |
|---|---|
| Quién carga | Solo el administrador de la inmobiliaria. Inquilino y propietario consultan/descargan sus contratos firmados; no cargan ni editan. |
| Firma | Está en el PDF. AARI no implementa firma electrónica, no solicita otra firma ni una fecha de firma manual. La inmobiliaria indica que el PDF cargado es la copia firmada. |
| Datos mínimos | Inquilino, propiedad asociada y fechas de inicio/fin. El PDF puede incorporarse después guardando primero un borrador. |
| Cláusulas | No se transcriben manualmente en HU29. Extracción y revisión corresponden a HU30/AARI-319, posterior a HU29. |
| Propietario histórico | El contrato conserva el ID del titular al registrarlo. Cambiar el dueño actual del inmueble no concede acceso a sus contratos anteriores. Los nombres de las fichas pueden actualizarse; el documento firmado conserva su contenido original. |
| Renovación | Nuevo contrato enlazado al anterior; no sobrescribe fechas ni archivos históricos. Debe corresponder al mismo inquilino y propiedad y comenzar después del período anterior. |
| Vigencia | Fechas inclusivas, con fin posterior al inicio. No se permiten períodos firmados superpuestos para una propiedad, incluidos períodos futuros e históricos. |
| Finalización | Se puede registrar una fecha dentro de la vigencia, no futura. Se preservan fechas pactadas y documentos; no desasocia automáticamente al inquilino. |
| Versiones | Cada subida agrega una versión y una ruta nueva. Nunca sobrescribe otra. Los participantes no pueden ver versiones que quedaron como borrador. |
| Baja de personas/inmuebles | Las FK impiden eliminar registros con contratos, incluso después de una desasociación. No se agrega borrado de contratos. |

Estas precisiones reemplazan la idea inicial de pedir fecha de firma y evitan
cargar datos que ya están en el documento. No cambian las 3 HH estimadas en Jira.
La secuencia funcional es **HU29 → HU30**; el vínculo de bloqueo invertido que
se detectó en Jira todavía requiere corregirse, sin duplicarlo.

## Componentes implementados

- `backend/migrations/20_contratos_alquiler.sql`: tablas `contratos`,
  `contrato_documentos` y `contrato_eventos`; restricciones, FK, índices,
  exclusión GiST de períodos y RLS.
- `backend/app/db/contratos.py`: consultas con alcance por participante,
  transacciones, bloqueo de fila y control de revisión para evitar cambios perdidos.
- `backend/app/services/contracts_service.py`: reglas, PDF válido, vigencia
  calculada según fecha argentina y coordinación entre base y Storage.
- `backend/app/services/contract_storage.py`: bucket privado
  `contratos-alquiler`, subida sin sobrescritura y URL firmada de **300 segundos**.
- `backend/app/api/contratos.py` y `schemas/contratos.py`: contrato HTTP.
- `frontend/src/features/contratos/`: listado paginado, búsqueda, carga,
  edición del borrador, detalle, PDF versionado, renovación y finalización.
- Integración con fichas de inquilino/propiedad y navegación administrativa.
  Portales `/inquilino/contratos` y `/propietario/contratos` de solo lectura.
- Dependencias nuevas: `pypdf==6.18.1` para validar el PDF y
  `tzdata==2026.4` para disponer de la zona horaria en Windows.
  `python-multipart` ya formaba parte de main; se instaló en el entorno local.

### Endpoints

| Método y ruta | Uso |
|---|---|
| `GET /contratos` | Listado paginado y filtrado; alcance impuesto por el usuario autenticado. |
| `POST /contratos` | Guardar borrador. |
| `GET /contratos/{id}` | Detalle y versiones visibles para ese usuario. |
| `PATCH /contratos/{id}` | Editar fechas del borrador con su revisión actual. |
| `POST /contratos/{id}/documentos` | Multipart: `archivo`, `firmado`, `revision`. |
| `POST /contratos/{id}/documentos/{documento_id}/descarga` | Obtener enlace privado temporal, después de autorizar el acceso. |
| `POST /contratos/{id}/finalizar` | Registrar finalización y conservar historial. |

No se devuelven rutas internas, hashes de archivos ni credenciales en el JSON.
Una persona ajena recibe 404 al pedir un contrato/documento por ID.
Los operadores no tienen acceso a este módulo.

## Seguridad y recuperación

- PDF hasta **10 MiB (10.485.760 bytes)**: se comprueba tamaño, extensión,
  tipo, cabecera, estructura legible y al menos una página. Se rechazan PDFs
  dañados o cifrados con contraseña; se admite PDF escaneado, sin ejecutar OCR.
- Bucket privado; tablas con RLS y permisos revocados a `public`, `anon`
  y `authenticated`. El backend es quien autoriza por rol y participantes.
- Verificación real posterior a la migración: las tres tablas tienen RLS,
  sin SELECT para anon/authenticated; bucket privado con límite correcto;
  **0 políticas en storage.objects**. No se agregaron políticas públicas.
- Borradores privados de la inmobiliaria; historial firmado accesible aunque
  el inquilino deje de ocupar el inmueble, sin dar acceso al nuevo ocupante.
- Cada escritura usa revisión. Si otra operación modificó el contrato,
  se rechaza con 409 y se pide recargar.
- Alta y subida son dos pasos: si falla el PDF, el borrador persiste y la
  interfaz lleva al detalle para reintentar sin repetir el alta.
- Si falla la persistencia después de subir, se intenta eliminar únicamente
  el objeto de esa operación. Ante un COMMIT incierto, no se borra si el documento
  existe o no se puede comprobar su estado.
- Una caída abrupta entre Storage y base puede dejar un objeto huérfano. No
  existe un recolector automático en esta HU: revisar el identificador de la
  operación en logs y cotejar base/Storage antes de eliminar nada.
- En despliegue, configurar también límite de cuerpo multipart en el proxy
  para evitar subidas enormes antes del control de tamaño del archivo.

## Pruebas y resultados

| Validación | Resultado |
|---|---|
| Backend local completo: `python -m pytest -q -p no:cacheprovider` | **279 passed, 19 skipped**. Las externas están desactivadas explícitamente. Incluye 6 pruebas del verificador de Storage con dobles. |
| PostgreSQL real aislado: `check_contracts_postgres.py --mode test` | **1 passed**; migración, repositorio, permisos, superposición inclusiva, FK restrictivas, finalización y renovación. Rollback verificado; sin esquema de prueba persistente. |
| Frontend completo: `npm test -- --pool=threads --maxWorkers=1` | **95 passed**, 23 archivos. Incluye 3 pruebas de la cabecera compartida. |
| Frontend específico HU29 | **11 passed**: fechas, PDF, multipart, borrador, subida fallida sin alta duplicada, renovación, lectura por rol y búsqueda fallida sin resultados viejos. |
| `npm run lint` / `npm run build` | Aprobados. |
| Navegador Chrome aislado, APIs simuladas | Listado, formulario y detalle en **12 anchos de 320 a 1920 px** con correo largo; 36 pantallas sin desborde horizontal ni errores de JavaScript. Alta de borrador, PDF firmado, portales de solo lectura y navegación de fechas con teclado. |
| Regresión de cabecera, `scripts/qa-header.mjs` | **156 combinaciones**: 6 módulos × 13 anchos × 2 longitudes de correo. Sin desborde global, superposición ni desplazamiento de la página al centrar el menú. Controles accesibles y navegación por teclado. |
| Storage real: `python scripts/check_contracts_storage.py --run` | Aprobado: PDF sintético subido, descarga firmada idéntica, accesos público/sin credenciales rechazados y objeto eliminado con ausencia verificada sin reutilizar caché. No modifica contratos ni personas. |
| `git diff --check` | Sin errores de formato. |
| `npm audit --omit=dev` | Sin vulnerabilidades de producción reportadas. |

La suite del backend cubre 53 casos nuevos locales de HU29, entre repositorio,
servicio, API, almacenamiento simulado, verificador externo con dobles y controles
estructurales de la migración.
No deben confundirse los controles de texto del SQL con la prueba PostgreSQL real.

Incidencias de validación resueltas:
- Los primeros selectores de prueba no contemplaban el asterisco del campo
  obligatorio; se corrigieron sin cambiar las etiquetas accesibles del formulario.
- Un parámetro de prueba generaba un identificador de 10 MiB; se le asignó un
  nombre corto. No fue un fallo de la regla de tamaño del PDF.
- Vitest en modo `forks` no pudo iniciar dos workers en Windows. Se ejecutó
  la **misma suite completa** con `threads`, sin excluir archivos ni pruebas.
- Se ajustó la alineación de Cancelar/Guardar tras la inspección visual.

Advertencias no bloqueantes de la suite: deprecación de TestClient/httpx y del
adaptador datetime de SQLite heredadas del entorno. No se modificaron módulos
ajenos para silenciarlas.

Auditoría de desarrollo: npm reportó 2 dependencias transitivas heredadas del
lockfile de main (`browserslist`, alta, y `baseline-browser-mapping`, moderada).
No se cambió el lockfile ni se ejecutó `npm audit fix`. Revisar su actualización
por separado; no aparecen en `npm audit --omit=dev`.

## Cómo reproducir y probar

Desde `backend/`, con el entorno activo y las dependencias instaladas:

```bash
python -m pip install -r requirements.txt
python -m pytest -q -p no:cacheprovider
python scripts/check_contracts_postgres.py --mode check
```

El último comando es de solo lectura. La prueba SQL externa requiere
autorización y se invoca con `--mode test`; la aplicación de una base nueva
requiere autorización y `--mode apply`. Para usar un `.env` de otro worktree,
pasarlo explícitamente con `--env-file RUTA`. Nunca incluir valores reales en
comandos, capturas ni documentación.

En el `backend/.env` del worktree deben estar `DATABASE_URL`, la configuración
de autenticación existente, `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.
Son variables **solo del backend**, nunca `VITE_*`. El entorno inicialmente
inspeccionado tenía DATABASE_URL, pero no las dos variables de Storage.
Se copió esa configuración local al nuevo worktree sin sobrescribir un .env
existente; el archivo permanece ignorado por Git. Las variables de Storage se
completaron en el worktree de HU29 el 13/09 y se verificaron con la prueba real.
Cada integrante debe configurarlas localmente en la rama que vaya a ejecutar.

`SUPABASE_URL` debe ser `https://project-ref.supabase.co`, obtenida del proyecto
en Supabase. No pegar ahí la conexión `postgresql://...`: esta corresponde
únicamente a `DATABASE_URL`. La clave `service_role` se usa solo del lado del
servidor. Después de guardar `.env`, detener y volver a levantar Uvicorn; la
recarga de código no garantiza recargar variables de entorno.

Prueba real de Storage, solo con autorización explícita:

```bash
python scripts/check_contracts_storage.py --run
```

Sin `--run` no se contacta Storage. La prueba crea un PDF sintético de una página
en memoria, lo sube a una ruta UUID exclusiva `qa-hu29/.../synthetic.pdf`, compara
los bytes descargados mediante URL firmada, comprueba que el acceso público/sin
autenticación falle, elimina solo ese objeto y verifica su ausencia. No crea
contratos, usuarios ni filas del dominio. No imprime claves ni enlaces firmados.
Si falla la limpieza, informa la ruta sintética exacta para revisarla, sin borrar
otros archivos. Sus controles y recuperación se prueban también con dobles.

En el primer intento real, subida, descarga y privacidad funcionaron, pero la
misma URL firmada devolvió una copia en caché después de eliminar el objeto.
Una lectura del catálogo confirmó **0 objetos `qa-hu29/` restantes**. Se corrigió
el verificador para comprobar la ausencia con un `cacheNonce` nuevo; la segunda
ejecución real aprobó todos los pasos y eliminó su propio archivo. Esto no
modifica el comportamiento del servicio ni promete revocación instantánea de
enlaces ya emitidos: la CDN puede conservar una respuesta temporalmente.
Referencia: [Supabase, Smart CDN](https://supabase.com/docs/guides/storage/cdn/smart-cdn).

Alcance de la evidencia: Storage se probó por HTTP real y PostgreSQL mediante la
prueba aislada descrita arriba; los recorridos de navegador utilizaron APIs
simuladas. Falta que el equipo reintente desde la interfaz tras reiniciar su
backend, sin confundir esas tres verificaciones con un único E2E real.

Levantar backend y frontend siguiendo el README, siempre con **localhost**
en ambos. Ingresar como administrador y abrir `/contratos`, o la ficha de un
inquilino/propiedad. La migración ya está instalada en el Supabase compartido.

QA visual optativa: `frontend/scripts/qa-contracts.mjs` requiere Playwright
y Chrome. Ejecutar después de `npm run build`, con un preview en
`http://localhost:5183`. `AARI_BROWSER_MODULES` permite indicar una instalación
externa de Playwright sin agregarla a producción. Las capturas son locales en
`backend/artifacts/hu29-ui/` y están ignoradas por Git.

### Corrección tras revisión visual del 13/09

Se reprodujo desborde de la cabecera al combinar los seis módulos con un correo
largo: a 1440 px, el documento alcanzaba 1577 px. La validación inicial de 9
pantallas usaba un correo corto y no cubría los anchos intermedios problemáticos.
Se sustituyó la distribución rígida por una grilla con buscador flexible y filas
adaptables; el perfil conserva el correo completo como nombre accesible y ayuda,
pero limita su ancho visual con puntos suspensivos. En móvil solo el menú tiene
desplazamiento interno, nunca toda la página. Se mantiene la guía visual AARI,
los tokens compartidos y controles táctiles de 44 px.

El centrado automático del enlace activo desplaza únicamente el menú, no el
documento; recalcula al cambiar tamaño o cargar la tipografía. La revisión visual
también exige que el perfil permanezca en la misma fila que la marca, evitando
que simplemente salte debajo del resto de la cabecera.

El error de PDF observado correspondió primero a variables de Storage ausentes
y luego a una URL PostgreSQL pegada en `SUPABASE_URL`. Es un problema de
configuración distinto de la suspensión de Supabase; no implica un PDF inválido.
No se modificaron credenciales ni datos del contrato desde las pruebas visuales.

## Pendientes antes del cierre

1. Crear el Pull Request de esta rama hacia main y realizar la revisión del equipo.
2. Conservar la distinción de evidencias: pruebas de Storage y PostgreSQL reales
   por separado y navegador simulado. Registrar también el recorrido manual de
   carga desde la interfaz cuando el equipo lo confirme explícitamente.
3. Resolver el vínculo de dependencia invertido en Jira cuando se disponga
   del mecanismo de edición adecuado.
4. Merge y cierre de HU solo con indicación explícita; no se cierran tareas
   automáticamente por publicar la rama.

No se hicieron llamadas a Gemini ni envíos de correos en esta implementación.

## Tiempo informado por el equipo

El 13/09 se imputaron **45 minutos del 12/09/2026**, repartidos según el avance
(no como cronometraje independiente por subtarea). La hora de inicio en Jira
es referencial para registrar el día correcto.

| Subtarea | Minutos | Worklog |
|---|---:|---|
| AARI-320 — Datos y migración | 10 | 10154 |
| AARI-321 — Storage privado | 5 | 10155 |
| AARI-322 — API y reglas | 10 | 10156 |
| AARI-323 — Interfaz | 10 | 10157 |
| AARI-324 — Versiones e historial | 5 | 10159 |
| AARI-325 — Pruebas | 5 | 10158 |
| **Total** | **45** | Sin duplicarlo en la HU padre |

El equipo informó **80 minutos adicionales el 13/09/2026**, registrados sin
duplicarlos en la HU padre. Se dio más peso a interfaz, Storage y pruebas, que
concentraron los ajustes de esta jornada. El reparto es orientativo, no un
cronometraje separado de cada subtarea; la hora de inicio es la hora de registro.

| Subtarea | Minutos adicionales | Worklog | Acumulado |
|---|---:|---|---:|
| AARI-323 — Interfaz responsive | 30 | 10160 | 40 min |
| AARI-321 — Storage privado | 20 | 10161 | 25 min |
| AARI-325 — Pruebas y documentación | 25 | 10162 | 30 min |
| AARI-322 — API y reglas | 5 | 10163 | 15 min |
| AARI-320 — Datos y migración | 0 | Sin nueva imputación | 10 min |
| AARI-324 — Versiones e historial | 0 | Sin nueva imputación | 5 min |
| **Total** | **80 min** | | **125 min (2 h 5 min)** |

Las estimaciones originales permanecen iguales. Jira descontó automáticamente
el tiempo trabajado de la estimación restante. La HU no se marca terminada
hasta que los cambios se revisen y fusionen.
