"""El dominio institucional sale de la configuración y se valida en un solo lugar."""

import pytest
from cryptography.fernet import Fernet

from app.core.config import Configuracion
from app.core.exceptions import ErrorAutenticacion, ErrorValidacion
from app.modules.auth.service import ServicioUsuarios

JWT = "secreto-de-prueba-solo-para-este-test-0123456789"


def _configuracion(dominios: str) -> Configuracion:
    return Configuracion(
        _env_file=None,
        JWT_SECRET=JWT,
        FERNET_KEY=Fernet.generate_key().decode(),
        DOMINIO_INSTITUCIONAL=dominios,
    )


def _servicio(dominios: str) -> ServicioUsuarios:
    servicio = ServicioUsuarios.__new__(ServicioUsuarios)
    servicio.db = None
    servicio.repositorio = None
    servicio.reloj = None
    servicio.validador_convocatoria = None
    servicio.configuracion = _configuracion(dominios)
    return servicio


def test_acepta_una_lista_de_dominios_separada_por_comas() -> None:
    configuracion = _configuracion(" UniHumboldt.edu.co , @humboldt.edu , ")

    assert configuracion.dominios_permitidos == ["unihumboldt.edu.co", "humboldt.edu"]
    assert configuracion.dominio_principal == "unihumboldt.edu.co"


def test_sin_dominio_configurado_la_aplicacion_no_arranca() -> None:
    with pytest.raises(ValueError, match="DOMINIO_INSTITUCIONAL no esta definida"):
        _configuracion("  ,  ")


@pytest.mark.parametrize(
    ("correo", "permitido"),
    [
        ("sgaribello_347@unihumboldt.edu.co", True),
        ("SGaribello@UNIHUMBOLDT.EDU.CO", True),
        ("ana@humboldt.edu", True),  # segundo dominio de la lista
        ("alguien@gmail.com", False),
        ("x@evil-unihumboldt.edu.co", False),  # termina parecido pero es otro dominio
        ("x@unihumboldt.edu.co.evil.com", False),
        ("unihumboldt.edu.co", False),
    ],
)
def test_la_validacion_de_dominio(correo, permitido) -> None:
    servicio = _servicio("unihumboldt.edu.co,humboldt.edu")

    assert servicio._dominio_permitido(correo) is permitido


def test_el_dominio_edu_co_acepta_cualquier_universidad_colombiana() -> None:
    servicio = _servicio("edu.co")

    assert servicio._dominio_permitido("ana@unihumboldt.edu.co") is True
    assert servicio._dominio_permitido("ana@estudiantes.otra.edu.co") is True
    assert servicio._dominio_permitido("ana@edu.co") is True
    assert servicio._dominio_permitido("ana@evil-edu.co") is False
    assert servicio._dominio_permitido("ana@gmail.com") is False
    assert servicio._dominio_permitido("ana@universidad.edu") is False


def test_registro_login_de_estudiante_y_alta_por_admin_usan_la_misma_validacion(
    monkeypatch,
) -> None:
    servicio = _servicio("unihumboldt.edu.co")
    llamadas = []
    original = ServicioUsuarios._dominio_permitido

    def espia(self, correo):
        llamadas.append(correo)
        return original(self, correo)

    monkeypatch.setattr(ServicioUsuarios, "_dominio_permitido", espia)

    with pytest.raises(ErrorValidacion):
        servicio.registrar("Ana", "ana@gmail.com", "clave-larga-1", "ESTUDIANTE")
    with pytest.raises(ErrorAutenticacion):
        servicio.login_estudiante("ana@gmail.com", "ABCD1234")
    with pytest.raises(ErrorValidacion):
        servicio.crear_usuario("Ana", "ana@gmail.com", None, "ESTUDIANTE", True)

    assert llamadas == ["ana@gmail.com"] * 3
