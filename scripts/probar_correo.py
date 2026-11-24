"""Envía un correo de prueba con el SMTP del .env, para comprobar que los códigos llegarán.

Uso (una línea):
    python scripts/probar_correo.py destinatario@ejemplo.com

Usa SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_REMITENTE, sin imprimir la
contraseña. Con EMAIL_BACKEND=console o fake solo avisa de que no hay envío real.
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from app.core.config import obtener_configuracion  # noqa: E402
from app.modules.notifications.adapters import SmtpAdapter  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Uso: python scripts/probar_correo.py destinatario@ejemplo.com")
        return 2
    config = obtener_configuracion()
    if config.email_backend != "smtp":
        print(f"EMAIL_BACKEND={config.email_backend}: no hay envio real. Ponlo en 'smtp'.")
        return 1
    usuario = config.smtp_user or "(sin login)"
    print(f"Enviando por {config.smtp_host}:{config.smtp_port} como {usuario}")
    try:
        SmtpAdapter().enviar(
            sys.argv[1],
            "Prueba de correo de Inter Nos",
            "<p>Si lees esto, el correo de Inter Nos <strong>funciona</strong>.</p>",
            "Si lees esto, el correo de Inter Nos funciona.",
        )
    except Exception as error:
        print(f"FALLA: {type(error).__name__}: {error}")
        return 1
    print("OK: correo enviado. Revisa la bandeja (y spam).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
