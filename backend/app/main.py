import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import require_admin, router as auth_router
from app.api.contratos import router as contratos_router
from app.services.contract_errors import ContractError
from app.api.inquilinos import property_router as property_tenant_router
from app.api.inquilinos import router as inquilinos_router
from app.api.operadores import router as operadores_router
from app.api.propiedades import router as propiedades_router
from app.api.propietarios import router as propietarios_router
from app.api.proveedores import router as proveedores_router
from app.api.proveedores import specialties_router
from app.api.reclamos import get_claim_notification_service
from app.api.reclamos import router as reclamos_router
from app.db.database import engine
from app.services.claim_notifications import run_notification_worker


def _notification_worker_enabled() -> bool:
    configured = os.getenv("NOTIFICATION_WORKER_ENABLED", "true").lower()
    return configured not in {"0", "false", "no"} and "PYTEST_CURRENT_TEST" not in os.environ


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Mantiene activa la bandeja de salida sin bloquear las peticiones."""

    if not _notification_worker_enabled():
        yield
        return

    stop_event = asyncio.Event()
    worker = asyncio.create_task(
        run_notification_worker(get_claim_notification_service(), stop_event)
    )
    try:
        yield
    finally:
        stop_event.set()
        await worker


app = FastAPI(
    title="AARI - Automatización y Asistencia en Reclamos Inmobiliarios",
    lifespan=lifespan,
)
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
app.include_router(operadores_router)
admin_dependencies = [Depends(require_admin)]
app.include_router(propiedades_router, dependencies=admin_dependencies)
app.include_router(property_tenant_router, dependencies=admin_dependencies)
app.include_router(propietarios_router, dependencies=admin_dependencies)
app.include_router(inquilinos_router, dependencies=admin_dependencies)
app.include_router(proveedores_router, dependencies=admin_dependencies)
app.include_router(specialties_router, dependencies=admin_dependencies)
app.include_router(reclamos_router)
app.include_router(contratos_router)


@app.exception_handler(ContractError)
async def contract_error_handler(request, error):
    detail = {"code": error.code, "message": str(error)}
    if error.field:
        detail["field"] = error.field
    return JSONResponse(status_code=error.status, content={"detail": detail})


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
