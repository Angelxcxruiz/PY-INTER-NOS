import smtplib

import pytest

from app.core.config import obtener_configuracion
from app.modules.notifications.adapters import (
    ConsolaAdapter,
    FakeAdapter,
    SmtpAdapter,
    crear_adapter_puerto,
)


def _con_backend(monkeypatch, valor: str) -> None:
    monkeypatch.setattr(obtener_configuracion(), "email_backend", valor)


@pytest.mark.parametrize(
    ("valor", "clase"),
    [("smtp", SmtpAdapter), ("fake", FakeAdapter), ("console", ConsolaAdapter)],
)
def test_backend_conocido_devuelve_su_adapter(monkeypatch, valor, clase) -> None:
    _con_backend(monkeypatch, valor)
    assert isinstance(crear_adapter_puerto(), clase)


def test_backend_desconocido_falla_en_lugar_de_enviar_a_consola(monkeypatch) -> None:
    _con_backend(monkeypatch, "mailpit")
    with pytest.raises(ValueError, match="EMAIL_BACKEND"):
        crear_adapter_puerto()


def test_smtp_incluye_remitente(monkeypatch) -> None:
    enviados = []

    class SmtpFalso:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def send_message(self, mensaje) -> None:
            enviados.append(mensaje)

    monkeypatch.setattr(smtplib, "SMTP", SmtpFalso)
    monkeypatch.setattr(obtener_configuracion(), "smtp_user", "")
    monkeypatch.setattr(obtener_configuracion(), "smtp_remitente", "no-reply@prueba.edu")

    SmtpAdapter().enviar("ana@prueba.edu", "Asunto", "<p>Hola</p>", "Hola")

    assert enviados[0]["From"] == "no-reply@prueba.edu"
    assert enviados[0]["To"] == "ana@prueba.edu"
