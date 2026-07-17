from fastapi import FastAPI

app = FastAPI(title="AARI - Automatización y Asistencia en Reclamos Inmobiliarios")


@app.get("/health")
def health_check():
    return {"status": "ok", "mensaje": "AARI backend funcionando correctamente"}