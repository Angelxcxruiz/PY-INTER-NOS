import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.enums import TipoEvento
from app.modules.notifications.models import EventoOutbox

CLAVES_SENSIBLES = {"codigo", "contrasena", "correo", "token", "password"}


def publicar(
    db: Session,
    tipo: str,
    agregado_tipo: str,
    agregado_id: str,
    payload: dict[str, Any],
) -> None:
    claves_encontradas = set(payload).intersection(CLAVES_SENSIBLES)
    if claves_encontradas:
        raise ValueError("El payload del outbox no puede contener datos sensibles")
    try:
        tipo_evento = TipoEvento(tipo)
    except ValueError as exc:
        raise ValueError("Tipo de evento no permitido") from exc

    # Hash de longitud fija: la clave en claro supera los 128 caracteres de la columna.
    clave_completa = f"{tipo_evento.value}:{agregado_tipo}:{agregado_id}:{sorted(payload.items())}"
    clave = hashlib.sha256(clave_completa.encode("utf-8")).hexdigest()
    existente = db.query(EventoOutbox).filter(EventoOutbox.clave_idempotencia == clave).first()
    if existente is not None:
        return

    evento = EventoOutbox(
        clave_idempotencia=clave,
        tipo=tipo_evento.value,
        agregado_tipo=agregado_tipo,
        agregado_id=agregado_id,
        payload=payload,
        estado="PENDIENTE",
        intentos=0,
        proximo_intento_en=ahora(),
        creado_en=ahora(),
    )
    db.add(evento)
    db.flush()
