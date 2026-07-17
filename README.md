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
(Pegar estructura)

## Cómo levantar el entorno de desarrollo (Backend)

### Requisitos previos
- Python 3.10 o superior instalado
- Git Bash (en Windows) o una terminal Unix

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

4. Instalá las dependencias:
```bash
   pip install -r requirements.txt
```

5. Levantá el servidor:
```bash
   uvicorn app.main:app --reload
```

6. Probá que funciona entrando a `http://127.0.0.1:8000/health` en el navegador.

## Cómo levantar el entorno de desarrollo (Frontend)

### Requisitos previos
- Node.js 18 o superior instalado
- Git Bash (en Windows) o una terminal Unix

### Pasos

1. Cloná el repositorio (si todavía no lo hiciste) y entrá a la carpeta `frontend`:
```bash
   git clone <url-del-repo>
   cd Proyecto-Final-AARI/frontend
```

2. Instalá las dependencias (solo la primera vez, o cuando se agregue una librería nueva):
```bash
   npm install
```

3. Levantá el servidor de desarrollo:
```bash
   npm run dev
```

4. Abrí `http://localhost:5173/` en el navegador para ver la aplicación.

## Estado del proyecto

En desarrollo - Sprint 0