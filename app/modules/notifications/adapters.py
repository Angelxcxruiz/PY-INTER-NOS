import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import obtener_configuracion

logger = logging.getLogger(__name__)


class PuertoCorreo(Protocol):
    def enviar(
        self,
        destinatario: str,
        asunto: str,
        html: str,
        texto: str,
    ) -> None: ...


class SmtpAdapter:
    def __init__(self) -> None:
        self.configuracion = obtener_configuracion()

    def enviar(
        self,
        destinatario: str,
        asunto: str,
        html: str,
        texto: str,
    ) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self.configuracion.smtp_remitente or (
            f"no-reply@{self.configuracion.dominio_institucional}"
        )
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto
        mensaje.set_content(texto)
        mensaje.add_alternative(html, subtype="html")
        with smtplib.SMTP(
            self.configuracion.smtp_host,
            self.configuracion.smtp_port,
            timeout=10,
        ) as smtp:
            if self.configuracion.smtp_user:
                smtp.starttls()
                smtp.login(
                    self.configuracion.smtp_user,
                    self.configuracion.smtp_password,
                )
            smtp.send_message(mensaje)


class ConsolaAdapter:
    def enviar(
        self,
        destinatario: str,
        asunto: str,
        html: str,
        texto: str,
    ) -> None:
        del html, texto
        logger.info("correo: destinatario=%s asunto=%s", destinatario, asunto)


class FakeAdapter:
    def __init__(self) -> None:
        self.envios: list[dict[str, str]] = []
        self.fallar = False
        self.error = "SMTP de prueba no disponible"

    def enviar(
        self,
        destinatario: str,
        asunto: str,
        html: str,
        texto: str,
    ) -> None:
        if self.fallar:
            raise RuntimeError(self.error)
        self.envios.append(
            {
                "destinatario": destinatario,
                "asunto": asunto,
                "html": html,
                "texto": texto,
            }
        )


def crear_adapter_puerto() -> PuertoCorreo:
    backend = obtener_configuracion().email_backend.lower()
    if backend == "smtp":
        return SmtpAdapter()
    if backend == "fake":
        return FakeAdapter()
    if backend in {"console", "consola"}:
        return ConsolaAdapter()
    raise ValueError(f"EMAIL_BACKEND no valido: '{backend}'. Use smtp, console o fake.")
