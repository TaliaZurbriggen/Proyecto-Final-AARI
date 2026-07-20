from fastapi import FastAPI
from sqlalchemy import text
from app.db.database import engine

app = FastAPI(title="AARI - Automatización y Asistencia en Reclamos Inmobiliarios")


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