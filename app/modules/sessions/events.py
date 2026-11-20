import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def publicar(
    db: Session,
    tipo: str,
    agregado_tipo: str,
    agregado_id: str,
    payload: dict[str, Any],
) -> None:
    del db
    # TODO [M6]: reemplazar este registro por insercion del evento en evento_outbox
    # dentro de la misma transaccion del servicio publicador.
    logger.info(
        "evento pendiente de outbox: tipo=%s agregado_tipo=%s agregado_id=%s",
        tipo,
        agregado_tipo,
        agregado_id,
    )
