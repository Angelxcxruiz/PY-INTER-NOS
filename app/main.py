from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.error_handlers import registrar_manejadores
from app.modules.auth.router import router as router_autenticacion
from app.modules.auth.router import router_administracion
from app.modules.cases.router import router as router_casos
from app.modules.evaluations.router import router as router_evaluaciones
from app.modules.notifications.router import router as router_notificaciones
from app.modules.participations.router import router as router_participaciones
from app.modules.reports.router import router as router_reportes
from app.modules.sessions.router import router as router_sesiones

DIRECTORIO_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
plantillas = Jinja2Templates(directory=str(DIRECTORIO_FRONTEND))

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
app.include_router(router_casos, prefix="/api/v1")
app.include_router(router_sesiones, prefix="/api/v1")
app.include_router(router_participaciones, prefix="/api/v1")
app.include_router(router_evaluaciones, prefix="/api/v1")
app.include_router(router_notificaciones, prefix="/api/v1")
app.include_router(router_reportes, prefix="/api/v1")
app.mount(
    "/app/static",
    StaticFiles(directory=str(DIRECTORIO_FRONTEND / "static")),
    name="static",
)


def _version_estaticos() -> str:
    marcas = [archivo.stat().st_mtime_ns for archivo in (DIRECTORIO_FRONTEND / "static").iterdir()]
    return str(max(marcas, default=0))


VERSION_ESTATICOS = _version_estaticos()


def _pagina(request: Request, plantilla: str) -> HTMLResponse:
    contexto = {"titulo_app": "Inter Nos", "version": VERSION_ESTATICOS}
    return plantillas.TemplateResponse(request, plantilla, contexto)


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/app/", response_class=HTMLResponse, include_in_schema=False)
def pagina_login(request: Request) -> HTMLResponse:
    return _pagina(request, "login.html")


@app.get("/app/docente", response_class=HTMLResponse, include_in_schema=False)
def pagina_docente(request: Request) -> HTMLResponse:
    return _pagina(request, "docente.html")


@app.get("/app/simulador", response_class=HTMLResponse, include_in_schema=False)
def pagina_simulador(request: Request) -> HTMLResponse:
    return _pagina(request, "simulador.html")


@app.get("/app/resultado", response_class=HTMLResponse, include_in_schema=False)
def pagina_resultado(request: Request) -> HTMLResponse:
    return _pagina(request, "resultado.html")


@app.get("/health")
def health() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"estado": "ok"}
