import os
from collections.abc import Generator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text

load_dotenv()

_test_database_url = os.getenv("TEST_DATABASE_URL")
if _test_database_url:
    os.environ["DATABASE_URL"] = _test_database_url
# Las pruebas procesan el outbox ellas mismas (con FakeAdapter): sin despacho en segundo plano.
os.environ["DESPACHO_INMEDIATO"] = "false"

from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.main import app


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
def cliente() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
