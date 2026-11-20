from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.error_handlers import registrar_manejadores
from app.modules.auth.router import router as router_autenticacion
from app.modules.auth.router import router_administracion

configuracion = obtener_configuracion()
app = FastAPI(
    title="Inter Nos",
    description="API del simulador de casos academicos de Psicologia Social",
    version="0.1.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configuracion.cors_origins_lista,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
registrar_manejadores(app)
app.include_router(router_autenticacion, prefix="/api/v1")
app.include_router(router_administracion, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"estado": "ok"}
