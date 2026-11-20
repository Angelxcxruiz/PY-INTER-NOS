from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.reports.service import ServicioReportes


def obtener_servicio_reportes(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioReportes:
    return ServicioReportes(db)
