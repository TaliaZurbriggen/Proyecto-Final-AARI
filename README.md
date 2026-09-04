# AARI - Automatización y Asistencia en Reclamos Inmobiliarios

Proyecto Final - Ingeniería en Sistemas de Información
Universidad Tecnológica Nacional - Facultad Regional San Francisco

## Integrantes

- Gasparotto Vietto, Tobías
- Zurbriggen, Talía Dianela

## Descripción

Sistema web con agente de inteligencia artificial que automatiza el flujo completo de gestión de reclamos de mantenimiento en inmobiliarias: clasificación ordinario/extraordinario/expensa, selección de proveedores, coordinación de turnos y seguimiento hasta el cierre.

## Stack tecnológico

- **Backend:** Python + FastAPI
- **Orquestación agéntica:** LangGraph
- **Base de datos:** PostgreSQL
- **Frontend:** React
- **Infraestructura:** AWS Free Tier / Railway
- **Gestión del proyecto:** Jira + Notion
- **Control de versiones:** GitHub

## Estructura del proyecto

```text
Proyecto-Final-AARI/
├── .agents/
│   └── skills/aari-frontend/   # Skill y referencia visual compartidas
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   └── classification/  # Grafo y estado del agente clasificador
│   │   │       ├── graph.py
│   │   │       ├── nodes.py
│   │   │       └── state.py
│   │   ├── api/                 # Rutas de la API
│   │   ├── core/                # Configuración compartida
│   │   ├── db/                  # Conexión a base de datos
│   │   ├── models/              # Modelos de persistencia
│   │   ├── schemas/             # Esquemas de entrada y salida
│   │   └── main.py              # Punto de entrada de FastAPI
│   ├── migrations/              # Esquema y datos iniciales de Supabase
│   ├── config/                  # Base de conocimiento configurable del clasificador
│   ├── prompts/                 # Prompt versionado del clasificador
│   ├── scripts/                 # Validadores locales sin dependencias externas
│   ├── tests/                   # Pruebas automatizadas
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── public/                  # Recursos estáticos
│   ├── src/
│   │   ├── components/          # UI y layouts reutilizables
│   │   ├── features/            # Auth, personas, inmuebles, proveedores y operadores
│   │   ├── pages/               # Pantallas generales de la aplicación
│   │   └── styles/              # Tokens y estilos globales
│   ├── AGENTS.md                # Reglas específicas del frontend
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml           # Levanta frontend y backend juntos
└── README.md
```

### Sistema visual del frontend

La identidad visual de AARI está centralizada para que los agentes y el equipo construyan pantallas consistentes:

- `.agents/skills/aari-frontend/`: skill que Codex detecta desde el repositorio, con criterios de diseño, accesibilidad y responsive.
- `frontend/AGENTS.md`: reglas obligatorias para cualquier cambio dentro del frontend.
- `frontend/src/styles/tokens.css`: fuente única de colores, tipografía, espaciado, radios y sombras.
- `frontend/src/components/`: componentes de interfaz y layout que deben reutilizarse antes de crear alternativas.
- `frontend/src/pages/DesignSystemPreview.jsx`: vista ejecutable para revisar la dirección visual y los estados principales.

La referencia aprobada se conserva dentro de la skill. Si una historia necesita apartarse de esa dirección, la decisión debe acordarse antes de implementarla.

### Agente de clasificación

El primer flujo del agente está implementado con LangGraph:

```text
Inicio → clasificar_reclamo → Fin
```

El grafo usa Gemini con salida estructurada, la base de conocimiento v1.1 y un umbral de confianza configurable (`0.75` inicial). Las respuestas inválidas o de confianza insuficiente se escalan de manera segura.

### Endpoint de clasificación

Con el backend levantado y un reclamo existente en Supabase, se puede ejecutar:

```bash
POST /reclamos/{reclamo_id}/clasificar
```

El endpoint obtiene el reclamo, invoca el grafo y guarda el resultado. Devuelve `Clasificado` o `Escalado`, junto con el tipo de gasto cuando corresponda, la confianza, el fundamento y el motivo de escalado. La migración `backend/migrations/06_clasificacion_agente.sql` debe haberse aplicado una vez antes de utilizarlo. Cada cambio de estado queda registrado con origen `agente`.

### Gestión de propietarios

El Sprint 2 incorpora el primer módulo funcional de administración. La API
expone alta, listado paginado con búsqueda, detalle con inmuebles asociados,
edición y eliminación de propietarios. La eliminación se bloquea cuando existen
propiedades relacionadas.

El frontend utiliza las rutas `/propietarios`, `/propietarios/nuevo`,
`/propietarios/:id` y `/propietarios/:id/editar`, con validaciones accesibles,
estados de carga/error/vacío y una presentación responsive.

Los nombres de propietarios e inquilinos admiten letras Unicode, espacios,
apóstrofes y guiones. Se rechazan valores numéricos o mezclas como `43428013`
y `Juan123` tanto en el frontend como en la API y la base de datos.

En instalaciones que ya ejecutaron el módulo de administración se debe aplicar
una vez `backend/migrations/07_propietarios_email_unico.sql`. La migración
normaliza el email y garantiza su unicidad sin reemplazar la migración original.

### Gestión de propiedades

La API de propiedades permite registrar, buscar, consultar, editar y eliminar
inmuebles asociados a un propietario. Cada ubicación registra provincia y
localidad obligatorias, y un barrio opcional que se guarda vacío cuando no
corresponde. Dirección, localidad y barrio deben contener al menos una letra:
se rechazan valores como `444`, pero se aceptan nombres reales que incluyen
números, como `Ruta 9`, `9 de Julio` o `Barrio 300 Viviendas`. La dirección se
normaliza para evitar duplicados que solo difieran en mayúsculas o espacios; su
identidad incluye provincia y localidad y, en departamentos, también el piso y
el número de unidad. El piso es un entero y `0` representa planta baja; la
unidad admite letras, números o combinaciones. La eliminación se bloquea cuando
existen reclamos históricos o un inquilino activo.

El frontend incorpora `/propiedades`, `/propiedades/nueva`,
`/propiedades/:id` y `/propiedades/:id/editar`. Las pantallas reutilizan el
sistema visual de AARI y conectan la navegación entre propiedades y
propietarios.

En bases existentes, la migración
`backend/migrations/08_propiedades_integridad.sql` debe aplicarse una vez para
normalizar los datos y reemplazar los índices de unicidad anteriores. Después
se aplica `backend/migrations/09_ubicacion_propiedades.sql`, que incorpora la
ubicación precisa y convierte el piso a entero. Si ya hubiera propiedades, la
migración 09 exige completar provincia y localidad antes de continuar. Por
último, `backend/migrations/10_ubicacion_propiedades_con_letras.sql` agrega las
restricciones de contenido descriptivo para dirección, localidad y barrio.

### Gestión de inquilinos

La API de inquilinos permite registrar, buscar, consultar, editar, desasociar y
eliminar personas inquilinas. El DNI y el email son únicos. En el alta se exige
una propiedad disponible y el sistema impide que dos inquilinos activos ocupen
el mismo inmueble. La edición permite cambiar la asociación o dejar al
inquilino con estado `sin_propiedad_asignada`; la eliminación se bloquea si el
registro tiene reclamos históricos.

El frontend incorpora `/inquilinos`, `/inquilinos/nuevo`,
`/inquilinos/:id` y `/inquilinos/:id/editar`, además del acceso al inquilino
activo desde la ficha de cada propiedad. Incluye listado paginado, búsqueda,
estados de carga/error/vacío, confirmaciones para acciones sensibles y diseño
responsive basado en el sistema visual compartido.

En bases existentes debe aplicarse una vez
`backend/migrations/11_inquilinos_integridad.sql`. La migración normaliza los
datos previos, valida la coherencia entre estado y propiedad y garantiza la
unicidad del email sin reemplazar el índice existente que limita una ocupación
activa por propiedad. A continuación se aplica
`backend/migrations/12_nombres_personas_validos.sql`, que incorpora el formato
de nombres a propietarios e inquilinos y se detiene si encuentra datos que no
puede corregir de manera segura.

### Gestión de proveedores

La API permite registrar, buscar, filtrar, consultar y editar proveedores, y
cambiar su estado entre activo e inactivo sin eliminar su historial. El
teléfono de WhatsApp se normaliza a formato internacional y es único. Cada
proveedor debe tener al menos una especialidad; el catálogo incluye oficios
predefinidos y admite especialidades personalizadas reutilizables.

La cobertura se registra de forma estructurada mediante una o más combinaciones
de provincia y localidad. En cada localidad se puede indicar cobertura completa
o una lista concreta de barrios. Esta estructura permite que la selección
automática de futuros reclamos filtre por ubicación sin interpretar texto
libre. Una propiedad sin barrio solo será compatible con proveedores que cubran
toda su localidad.

El horario habitual de inicio y fin es opcional y solo funciona como referencia
operativa. No representa turnos disponibles ni reemplaza la coordinación de
visitas prevista para el módulo agéntico. Si se informa, ambos horarios son
obligatorios y el fin debe ser posterior al inicio dentro del mismo día.

El frontend incorpora `/proveedores`, `/proveedores/nuevo`,
`/proveedores/:id` y `/proveedores/:id/editar`. Incluye filtros combinables por
especialidad, provincia, localidad, barrio y estado, además de pantallas
responsive para alta, edición, detalle y activación o desactivación. El filtro
por barrio exige indicar también provincia y localidad para evitar coincidencias
entre barrios homónimos o proveedores que cubren otra ciudad completa.

Las cinco tablas del módulo de proveedores tienen RLS habilitado y no conceden
permisos a los roles `anon` ni `authenticated` del Data API de Supabase. La
aplicación accede a ellas exclusivamente mediante FastAPI y la conexión segura
del backend; no se definen políticas públicas para acceso directo.

En bases existentes, la actualización se realiza en dos etapas. La migración
`backend/migrations/15_proveedores_cobertura_horario.sql` crea las coberturas
estructuradas y conserva temporalmente `zona_cobertura` para revisar los datos
anteriores. Después de completar la cobertura de cada proveedor se ejecuta
`backend/migrations/16_finalizar_cobertura_proveedores.sql`, que verifica que
no falten datos antes de eliminar la columna libre. El procedimiento y la
consulta de control están documentados en `backend/migrations/README.md`.

### Autenticación del administrador

El acceso administrativo utiliza `POST /auth/login`, una sesión JWT almacenada
en una cookie `httpOnly` y autorización por rol. Tres intentos fallidos
consecutivos bloquean temporalmente la cuenta durante 15 minutos. El frontend
expone `/login`, recupera la sesión con `GET /auth/me` y la elimina mediante
`POST /auth/logout`.

Para ejecutar el flujo se deben configurar `JWT_SECRET` con al menos 32
caracteres y, opcionalmente, `JWT_EXPIRE_MINUTES`. En bases existentes debe
aplicarse una vez `backend/migrations/13_autenticacion_usuarios.sql`. En
producción, `ENVIRONMENT` debe usar un valor distinto de `development`,
`local` o `test` para que la cookie se emita con el atributo `Secure`.

### Acceso de propietarios e inquilinos

Al registrar un propietario o inquilino, el backend crea en la misma
transacción una cuenta vinculada. El email es el usuario y el DNI se utiliza
como contraseña temporal protegida con `pgcrypto`. En el primer ingreso la
persona debe reemplazarla por una contraseña de al menos 8 caracteres y un
número antes de acceder a su portal. Después del cambio, la contraseña temporal
deja de ser válida y la navegación dirige a cada persona según su rol.

El correo de bienvenida se configura con `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` y
`APP_LOGIN_URL`. Si SMTP no está disponible, el alta y la cuenta se conservan:
el estado queda como `fallido` y administración puede reintentar el envío desde
la ficha del propietario o inquilino. Las pruebas automatizadas usan dobles y
no envían correos reales.

Para usar el correo institucional del proyecto en desarrollo, cada integrante
debe copiar estas variables únicamente en `backend/.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=proyectofinalaari@gmail.com
SMTP_PASSWORD=LA_CLAVE_DE_APLICACION
SMTP_FROM=AARI <proyectofinalaari@gmail.com>
SMTP_STARTTLS=true
APP_LOGIN_URL=http://localhost:5173/login
```

`SMTP_PASSWORD` debe contener una contraseña de aplicación de Google generada
para la cuenta del proyecto, no su contraseña normal. El valor real se comparte
por un medio seguro y nunca se guarda en Git, Jira, Notion ni capturas. En el
archivo `.env` solo deben existir asignaciones `CLAVE=VALOR` y comentarios que
comiencen con `#`; no se deben pegar encabezados como `=== backend/.env ===`.
Estas variables no pertenecen a `frontend/.env`. Para un entorno publicado,
`APP_LOGIN_URL` debe reemplazarse por la URL real del login.

Las bases existentes deben aplicar una vez
`backend/migrations/14_acceso_propietarios_inquilinos.sql`. La migración crea y
vincula cuentas faltantes usando el DNI vigente como clave temporal, registra
los envíos previos como pendientes y se detiene ante emails de acceso
duplicados para no inferir una identidad incorrecta.

### Gestión de operadores (HU7)

Administración dispone de `/operadores` y `/operadores/nuevo` para listar,
buscar, registrar y desactivar operadores. El alta solicita nombre completo y
email único entre todas las cuentas, incluidas las inactivas. Genera una
contraseña aleatoria de ocho caracteres con letras y números: se guarda su
hash con `pgcrypto`, se envía por correo y debe cambiarse en el primer ingreso.
La contraseña no se devuelve a la interfaz ni se registra en logs.

La API, disponible exclusivamente para el rol administrador, expone:

- `GET /usuarios/operadores` — búsqueda y paginación.
- `POST /usuarios/operadores` — alta y envío de credenciales.
- `POST /usuarios/operadores/{id}/acceso/reintentar` — nueva clave temporal y
  reenvío, solamente mientras la cuenta esté activa y pendiente de primer ingreso.
- `PATCH /usuarios/operadores/{id}/desactivar` — baja lógica y cantidad de
  reclamos liberados.

Se reutilizan las variables SMTP y `APP_LOGIN_URL` de HU6: **no hay variables
de entorno ni dependencias nuevas**. El alta se confirma antes de contactar a
SMTP. Si el correo falla, la cuenta permanece y el listado permite reintentar.
Cada reenvío invalida la clave temporal anterior, incluso si el nuevo correo
falla; una confirmación advierte este comportamiento. Si un envío queda
pendiente por una interrupción, se puede reintentar después de dos minutos.
Nunca se conserva la clave temporal recuperable para reenviarla.

Desactivar impide nuevos accesos e invalida la sesión en su siguiente consulta
autenticada. En la misma transacción, los reclamos asignados al operador que
estén en estado `Escalado` quedan sin asignación, disponibles para la futura
cola general; no cambian de estado ni se eliminan. Los demás reclamos conservan
su asignación histórica. La bandeja de reclamos, la edición y la reactivación
de operadores quedan fuera de esta HU.

La migración `backend/migrations/17_usuarios_operadores.sql` se aplicó con
autorización al Supabase compartido de desarrollo de AARI el 02/09/2026.
Talía no debe repetirla en ese mismo proyecto; cambiar de rama o hacer pull no
ejecuta migraciones. Para otras bases, seguir `backend/migrations/README.md`.
La revisión del PR #21 agrega `backend/migrations/18_revalidar_operador_al_escalar.sql`,
**aplicada con autorización el 03/09/2026** en la base compartida, registrada como
`20260904001512_hu7_revalidar_operador_al_escalar`. No repetirla en ese proyecto.
Revalida el operador al entrar a `Escalado` aunque solo cambie el estado:
si está inactivo, la
operación se rechaza; se permite reabrir con otro operador activo o sin asignación.
No cambia asignaciones históricas ni reescribe la migración 17. Se detiene ante
escalados existentes con operador inválido para que se revisen por separado.
Las pruebas aisladas de HU7 están en
`backend/tests/test_operadores.py` y
`frontend/src/features/operadores/pages/Operadores.test.jsx`; no envían correo
ni acceden a Supabase. `backend/tests/test_operadores_migration.py` agrega
controles estructurales locales de la migración 18, no una ejecución de su SQL.
Las pruebas optativas de PostgreSQL real están en
`backend/tests/test_operadores_supabase_integration.py`: validan el flujo con
rollback y la concurrencia en un esquema privado temporal; ahora incluyen
reaperturas y su concurrencia con la baja, y requieren la migración 18 instalada.
El procedimiento, los resultados y las advertencias previas están en
`docs/hu7_validacion_supabase.md`.
Se validó un alta real autorizada mediante el servicio de operadores y SMTP:
cuenta persistida, hash bcrypt, primer ingreso obligatorio y correo registrado
como enviado en un intento. Quedan la confirmación de recepción, el primer
ingreso y la revisión manual de la interfaz por el responsable.

### Pruebas automáticas del clasificador

Desde `backend/`, la suite completa se ejecuta con:

```bash
python -m pytest -q
```

Las pruebas automatizadas usan proveedores y repositorios controlados: no
consumen cuota de Gemini ni modifican Supabase. Incluyen recorridos integrados
del endpoint, el servicio y el LangGraph real, además de una prueba de aceptación
que reproduce la precisión final del prompt v5 a partir de los 80 resultados ya
guardados. La evidencia detallada está en
`docs/evaluaciones/aari112/informe_final_v5.md` y
`docs/evaluaciones/aari113/informe_pruebas.md`.

## Cómo levantar el entorno de desarrollo (Backend)

### Requisitos previos
Antes de seguir las instrucciones de abajo, asegurate de tener instalado:

1. **Git** — para clonar el repositorio y manejar versiones.
   - Descarga: https://git-scm.com/download/win
   - Verificar instalación: `git --version`
   - En Windows, usar **Git Bash** como terminal (viene incluido en la instalación) en vez de PowerShell o CMD, para que los comandos de este README funcionen tal cual están escritos.

2. **Python 3.10 o superior** — para correr el backend.
   - Descarga: https://www.python.org/downloads/
   - Verificar instalación: `python --version`

3. **Node.js 22.22 o superior** — para correr el frontend.
   - Descarga: https://nodejs.org/ (elegir la versión LTS)
   - Verificar instalación: `node --version` y `npm --version`

4. **Docker Desktop** — para correr el proyecto con contenedores (opcional para desarrollo básico, pero recomendado).
   - Descarga: https://www.docker.com/products/docker-desktop/
   - Requiere WSL2 en Windows — el instalador de Docker guía este paso, o se puede instalar antes manualmente con `wsl --install` desde PowerShell como administrador.
   - Verificar instalación: `docker --version`
   - Después de instalar, abrir Docker Desktop y esperar a que la esquina inferior izquierda diga "Engine running" antes de usar comandos `docker`.
   - **Importante:** puede pedir reiniciar la computadora más de una vez durante la instalación (por WSL2). Es normal.

Una vez instalado todo esto, segui con las secciones de abajo.

### Pasos

1. Cloná el repositorio y entrá a la carpeta `backend`:
```bash
   git clone <url-del-repo>
   cd Proyecto-Final-AARI/backend
```

2. Creá el entorno virtual (solo la primera vez):
```bash
   python -m venv venv
```

3. Activá el entorno virtual (cada vez que trabajes en el proyecto):
```bash
   source venv/Scripts/activate
```
   Vas a ver `(venv)` al principio de la línea de la terminal si funcionó.

4. Copiá el archivo de variables de entorno de ejemplo y completalo con tus valores reales:
```bash
   cp .env.example .env
```
   Vas a necesitar la connection string de Supabase y las claves de API (pedíselas a tu compañero de equipo).

5. Completá `DATABASE_URL` en tu `.env` con la connection string de Supabase (pedísela a un compañero del equipo). Tené en cuenta:
   - Sacá el parámetro `?pgbouncer=true` del final si lo copiaste directo desde Supabase — `psycopg2` no lo reconoce y falla la conexión.
   - Si la contraseña de la base de datos tiene caracteres especiales (`%`, `#`, `!`, `+`, espacios, etc.), hay que codificarlos (URL encoding) o la conexión no va a parsear bien. Tabla de reemplazos común:
     | Carácter | Reemplazo |
     |----------|-----------|
     | `%`      | `%25`     |
     | `#`      | `%23`     |
     | `!`      | `%21`     |
     | `+`      | `%2B`     |
     | espacio  | `%20`     |

6. Probá la conexión levantando el servidor y entrando a `http://localhost:8000/health/db`. Si ves `{"status":"ok",...}`, la conexión funciona.

7. Instalá las dependencias:
```bash
   pip install -r requirements.txt
```

8. Levantá el servidor:
```bash
   uvicorn app.main:app --reload
```

9. Probá que funciona entrando a `http://localhost:8000/health` en el navegador.

### Alternativa: levantar el backend con Docker

Si preferís no instalar Python localmente, podés usar Docker:

```bash
cd backend
docker build -t aari-backend .
docker run -p 8000:8000 --env-file .env aari-backend
```

## Cómo levantar el entorno de desarrollo (Frontend)

### Pasos

1. Cloná el repositorio (si todavía no lo hiciste) y entrá a la carpeta `frontend`:
```bash
   git clone <url-del-repo>
   cd Proyecto-Final-AARI/frontend
```
2. Copiá el archivo de variables de entorno de ejemplo:
```bash
   cp .env.example .env
```

3. Instalá las dependencias (solo la primera vez, o cuando se agregue una librería nueva):
```bash
   npm install
```

4. Levantá el servidor de desarrollo:
```bash
   npm run dev
```

5. Abrí `http://localhost:5173/` en el navegador para ver la aplicación.

> En desarrollo local usá `localhost` tanto para el frontend como para el
> backend. No mezcles `localhost` con `127.0.0.1`: el navegador los considera
> sitios diferentes y puede impedir que la cookie de sesión se envíe después
> del inicio de sesión. El valor recomendado es
> `VITE_API_URL=http://localhost:8000`.

### Validaciones del frontend

Desde `frontend/`:

```bash
npm run lint
npm run test
npm run build
```

Las pruebas usan respuestas HTTP simuladas y no modifican Supabase.

### Alternativa: levantar el frontend con Docker

Si preferís no instalar Node localmente, podés usar Docker:

```bash
cd frontend
docker build -t aari-frontend .
docker run -p 5173:5173 aari-frontend
```
## Cómo levantar el proyecto completo (recomendado)

Con Docker Compose podés levantar el backend y el frontend juntos, ya conectados entre sí, con un solo comando.

### Requisitos
- Docker Desktop instalado y corriendo (ver "Requisitos previos" abajo)
- Los archivos `.env` creados en `backend/` y `frontend/` (a partir de sus `.env.example`, con los valores reales completados)

### Pasos

1. Cloná el repositorio:
```bash
   git clone <url-del-repo>
   cd Proyecto-Final-AARI
```

2. Levantá todo:
```bash
   docker-compose up --build
```

3. Accedé a:
   - Frontend: http://localhost:5173/
   - Backend: http://localhost:8000/health y http://localhost:8000/health/db

4. Para detener todo, presioná `Ctrl + C` en la terminal.

> Las secciones de abajo explican cómo levantar cada parte por separado, sin Docker, si lo preferís para desarrollar.

## Estado del proyecto

**Sprint 2 — En curso (18/08/2026 al 15/09/2026)**

- **Sprint 1 finalizado:** grafo LangGraph, integración con Gemini, clasificación estructurada, umbral de confianza, persistencia trazable, manejo seguro de respuestas inválidas y evaluación del prompt v5 sobre 80 casos (70/80; 87,50 %).
- **Base compartida del Sprint 2 completada:** sistema visual, skill de frontend, tokens y componentes reutilizables.
- **Completada y fusionada:** AARI-9 / HU1, gestión integral de propietarios.
- **Completada y fusionada:** AARI-22 / HU2, gestión integral de propiedades.
- **Completada y fusionada:** AARI-56 / HU5, autenticación administrativa.
- **Completada y fusionada:** AARI-68 / HU6, acceso de propietarios e inquilinos.
- **En curso:** AARI-79 / HU7, gestión de operadores; migraciones 17 y 18
  aplicadas, 16 pruebas PostgreSQL aprobadas y corrección de reapertura del PR #21
  pendiente de nueva revisión. Alta real con SMTP validada desde el servicio;
  pendientes la confirmación de recepción, el primer ingreso y la revisión manual.
- **En curso:** AARI-34 / HU3, gestión integral de inquilinos; implementación
  terminada y pendiente de revisión antes del Pull Request.
- **Siguiente secuencia del módulo de administración:** proveedores.
- **Trabajo paralelo:** autenticación, acceso por roles, operadores y alta de reclamos.
