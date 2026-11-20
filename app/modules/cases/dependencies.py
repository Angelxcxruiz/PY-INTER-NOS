from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.cases.service import ServicioCasos
from app.shared.dependencias_autenticacion import obtener_sesion


def obtener_servicio_casos(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioCasos:
    return ServicioCasos(db)


def obtener_sesion_actual(
    sesion: Annotated[dict, Depends(obtener_sesion)],
) -> dict:
    return sesion
