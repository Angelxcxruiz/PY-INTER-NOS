from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.sessions.service import ServicioSesiones


def obtener_servicio_sesiones(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioSesiones:
    return ServicioSesiones(db)
