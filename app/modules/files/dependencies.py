from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.cases.service import ServicioCasos
from app.modules.files.service import ServicioArchivos


def obtener_servicio_archivos(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioArchivos:
    # La regla "no borrar una imagen en uso" la responde el servicio de casos.
    return ServicioArchivos(db, esta_en_uso=ServicioCasos(db).archivo_en_uso)
