import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import require_admin, router as auth_router
from app.api.inquilinos import property_router as property_tenant_router
from app.api.inquilinos import router as inquilinos_router
from app.api.propiedades import router as propiedades_router
from app.api.propietarios import router as propietarios_router
from app.api.reclamos import router as reclamos_router
from app.db.database import engine

app = FastAPI(title="AARI - Automatización y Asistencia en Reclamos Inmobiliarios")
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
admin_dependencies = [Depends(require_admin)]
app.include_router(propiedades_router, dependencies=admin_dependencies)
app.include_router(property_tenant_router, dependencies=admin_dependencies)
app.include_router(propietarios_router, dependencies=admin_dependencies)
app.include_router(inquilinos_router, dependencies=admin_dependencies)
app.include_router(reclamos_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "mensaje": "AARI backend funcionando correctamente"}


@app.get("/health/db")
def health_check_db():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "mensaje": "Conexión a la base de datos exitosa"}
    except Exception as e:
        return {"status": "error", "mensaje": str(e)}
