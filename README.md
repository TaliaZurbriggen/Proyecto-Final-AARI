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
│   ├── src/                     # Aplicación React
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml           # Levanta frontend y backend juntos
└── README.md
```

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

3. **Node.js 18 o superior** — para correr el frontend.
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

6. Probá la conexión levantando el servidor y entrando a `http://127.0.0.1:8000/health/db`. Si ves `{"status":"ok",...}`, la conexión funciona.

7. Instalá las dependencias:
```bash
   pip install -r requirements.txt
```

8. Levantá el servidor:
```bash
   uvicorn app.main:app --reload
```

9. Probá que funciona entrando a `http://127.0.0.1:8000/health` en el navegador.

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

**Sprint 1 — En curso**

- Completado: base del proyecto, migraciones SQL, backend FastAPI, frontend React y entorno Docker.
- Completado: grafo inicial de clasificación con LangGraph y su prueba automatizada.
- Completado: integración con Gemini, clasificación estructurada, umbral de confianza y manejo seguro de respuestas inválidas.
- Implementado y validado en rama: endpoint y persistencia trazable (AARI-109); pendiente de commit y PR.
