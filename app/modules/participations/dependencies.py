from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.participations.service import ServicioParticipaciones


def obtener_servicio_participaciones(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioParticipaciones:
    return ServicioParticipaciones(db)
