from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.evaluations.service import ServicioEvaluaciones


def obtener_servicio_evaluaciones(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioEvaluaciones:
    return ServicioEvaluaciones(db)
