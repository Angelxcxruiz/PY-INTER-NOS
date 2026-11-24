from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.service import ServicioUsuarios
from app.modules.notifications.service import despachar_outbox
from app.modules.sessions.validacion import validador_convocatoria_por_defecto
from app.shared.dependencias_autenticacion import obtener_sesion_basica


def obtener_despacho() -> Callable[[], int]:
    """Función que envía los correos pendientes tras responder (se puede sustituir en pruebas)."""
    return despachar_outbox


def obtener_servicio(db: Annotated[Session, Depends(get_db)]) -> ServicioUsuarios:
    return ServicioUsuarios(
        db,
        validador_convocatoria=validador_convocatoria_por_defecto(db),
    )


def obtener_usuario_actual(
    sesion: Annotated[dict, Depends(obtener_sesion_basica)],
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
):
    # /auth/me debe funcionar también con la cuenta en revisión: es como se ve el estado.
    return servicio.usuario_actual(str(sesion["sub"]))
