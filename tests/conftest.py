import os
import tempfile
import uuid
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import delete, text

load_dotenv()

_test_database_url = os.getenv("TEST_DATABASE_URL")
if _test_database_url:
    os.environ["DATABASE_URL"] = _test_database_url
# Las pruebas procesan el outbox ellas mismas (con FakeAdapter): sin despacho en segundo plano.
os.environ["DESPACHO_INMEDIATO"] = "false"
# Las imágenes que suben las pruebas van a una carpeta temporal, nunca a uploads/.
os.environ["ALMACENAMIENTO_DIR"] = tempfile.mkdtemp(prefix="inter_nos_uploads_")
os.environ["ALMACENAMIENTO_BACKEND"] = "local"
# Las pruebas nunca usan la clave real de .env ni llaman a Google: esta clave es falsa.
os.environ["GEMINI_API_KEY"] = "AQ.clave-falsa-de-prueba-0123456789"
os.environ["GENERACION_IMAGENES_ACTIVA"] = "true"

from ayudas_editor import _cabeceras, _docente

from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.main import app
from app.modules.auth.models import Usuario
from app.modules.cases.models import Caso
from app.modules.files.models import ArchivoAdjunto


@pytest.fixture(scope="session")
def base_real() -> None:
    configuracion = obtener_configuracion()
    if not configuracion.test_database_url:
        raise RuntimeError(
            "TEST_DATABASE_URL no esta definida. Copia .env.example a .env "
            "y configura una base MySQL real para pruebas."
        )

    with SessionLocal() as db:
        db.execute(text("SELECT 1"))


@pytest.fixture
def db(base_real) -> Generator:
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def taller(cliente, db):
    """Un docente con un caso borrador de dos escenarios, y otro docente aparte."""
    sufijo = uuid.uuid4().hex[:8]
    docente, otro = _docente(db, sufijo), _docente(db, f"{sufijo}x")
    cabeceras = _cabeceras(docente.id)
    caso = cliente.post(
        "/api/v1/cases",
        headers=cabeceras,
        json={
            "nombre": "Caso con composición",
            "desarrollo_situacional": "d",
            "contexto_historia": "c",
            "tiempo_estimado_min": 30,
        },
    )
    assert caso.status_code == 201, caso.text
    caso_id = caso.json()["id"]
    escenarios = [
        cliente.post(
            f"/api/v1/cases/{caso_id}/escenarios",
            headers=cabeceras,
            json={"titulo": f"E{n}", "contexto": "contexto"},
        ).json()["id"]
        for n in (1, 2)
    ]
    yield {
        "cabeceras": cabeceras,
        "otro": _cabeceras(otro.id),
        "docente_id": docente.id,
        "otro_id": otro.id,
        "caso_id": caso_id,
        "escenarios": escenarios,
    }
    db.rollback()
    db.execute(delete(Caso).where(Caso.id == caso_id))
    db.execute(delete(ArchivoAdjunto).where(ArchivoAdjunto.docente_id.in_([docente.id, otro.id])))
    db.execute(delete(Usuario).where(Usuario.id.in_([docente.id, otro.id])))
    db.commit()


@pytest.fixture
def cliente() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
