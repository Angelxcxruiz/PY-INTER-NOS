import hashlib

import pytest
from cryptography.fernet import Fernet

from app.core import config
from app.core.config import MARCADOR_SECRETO, Configuracion

CLAVE_FERNET_VALIDA = Fernet.generate_key().decode()
JWT_VALIDO = "secreto-de-prueba-solo-para-este-test-0123456789"


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.delenv("DOMINIO_INSTITUCIONAL", raising=False)


def crear(**valores) -> Configuracion:
    # _env_file=None: la prueba no debe leer el .env real de quien la ejecuta.
    valores.setdefault("DOMINIO_INSTITUCIONAL", "prueba.edu")
    return Configuracion(_env_file=None, **valores)


def test_con_secretos_propios_arranca() -> None:
    configuracion = crear(JWT_SECRET=JWT_VALIDO, FERNET_KEY=CLAVE_FERNET_VALIDA)

    assert configuracion.jwt_secreto == JWT_VALIDO


def test_sin_secretos_falla_con_mensaje_claro() -> None:
    with pytest.raises(ValueError) as error:
        crear()

    mensaje = str(error.value)
    assert "JWT_SECRET no esta definida" in mensaje
    assert "FERNET_KEY no esta definida" in mensaje
    assert "Fernet.generate_key()" in mensaje


@pytest.mark.parametrize(
    "jwt_secreto", [MARCADOR_SECRETO, "cambiar-en-entorno", "cambiar-por-un-secreto-largo"]
)
def test_jwt_de_ejemplo_es_rechazado(jwt_secreto) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET sigue con un valor de ejemplo"):
        crear(JWT_SECRET=jwt_secreto, FERNET_KEY=CLAVE_FERNET_VALIDA)


def test_fernet_de_ejemplo_es_rechazado() -> None:
    with pytest.raises(ValueError, match="FERNET_KEY sigue con un valor de ejemplo"):
        crear(JWT_SECRET=JWT_VALIDO, FERNET_KEY=MARCADOR_SECRETO)


def test_clave_fernet_publicada_es_rechazada_por_su_huella(monkeypatch) -> None:
    clave_filtrada = Fernet.generate_key().decode()
    huella = hashlib.sha256(clave_filtrada.encode("utf-8")).hexdigest()
    monkeypatch.setattr(config, "_HUELLAS_RECHAZADAS", {huella})

    with pytest.raises(ValueError, match="FERNET_KEY sigue con un valor de ejemplo o publicado"):
        crear(JWT_SECRET=JWT_VALIDO, FERNET_KEY=clave_filtrada)


def test_fernet_con_formato_invalido_es_rechazado() -> None:
    with pytest.raises(ValueError, match="FERNET_KEY no es una clave Fernet valida"):
        crear(JWT_SECRET=JWT_VALIDO, FERNET_KEY="no-es-una-clave")


def test_el_mensaje_de_error_no_filtra_los_secretos() -> None:
    with pytest.raises(ValueError) as error:
        crear(
            JWT_SECRET=MARCADOR_SECRETO,
            FERNET_KEY=CLAVE_FERNET_VALIDA,
            DOCENTE_PASSWORD="contrasena-que-no-debe-aparecer",
        )

    mensaje = str(error.value)
    assert "contrasena-que-no-debe-aparecer" not in mensaje
    assert CLAVE_FERNET_VALIDA not in mensaje


def test_secreto_en_blanco_cuenta_como_ausente() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET no esta definida"):
        crear(JWT_SECRET="   ", FERNET_KEY=CLAVE_FERNET_VALIDA)
