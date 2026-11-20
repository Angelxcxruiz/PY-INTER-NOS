from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.service import ServicioUsuarios
from app.shared.dependencias_autenticacion import obtener_sesion


def obtener_servicio(db: Annotated[Session, Depends(get_db)]) -> ServicioUsuarios:
    return ServicioUsuarios(db)


def obtener_usuario_actual(
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
):
    return servicio.usuario_actual(str(sesion["sub"]))
