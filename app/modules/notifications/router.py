from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.notifications.dependencies import obtener_servicio_notificaciones
from app.modules.notifications.schemas import (
    EntregaCorreoSalida,
    NotificacionSalida,
)
from app.modules.notifications.service import ServicioNotificaciones
from app.shared.dependencias_autenticacion import obtener_sesion

router = APIRouter(tags=["M6 - Notificaciones"])


@router.get("/notificaciones", response_model=list[NotificacionSalida])
def listar_notificaciones(
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
    no_leidas: bool = False,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificacionSalida]:
    return [
        NotificacionSalida.model_validate(notificacion)
        for notificacion in servicio.listar(
            sesion,
            no_leidas,
            limite,
            desplazamiento,
        )
    ]


@router.get("/notificaciones/contador")
def contador_notificaciones(
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
) -> dict[str, int]:
    return {"contador": servicio.contador(sesion)}


@router.post(
    "/notificaciones/{notificacion_id}/leer",
    response_model=NotificacionSalida,
)
def leer_notificacion(
    notificacion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
) -> NotificacionSalida:
    return NotificacionSalida.model_validate(servicio.marcar_leida(notificacion_id, sesion))


@router.post("/notificaciones/leer-todas")
def leer_todas(
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
) -> dict[str, int]:
    return {"marcadas": servicio.marcar_todas_leidas(sesion)}


@router.get(
    "/sessions/{sesion_id}/entregas",
    response_model=list[EntregaCorreoSalida],
)
def entregas_sesion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
) -> list[EntregaCorreoSalida]:
    return [
        EntregaCorreoSalida.model_validate(entrega)
        for entrega in servicio.entregas_sesion(sesion_id, sesion)
    ]


@router.post(
    "/sessions/{sesion_id}/convocatorias/{convocatoria_id}/reenviar",
)
def reenviar_invitacion(
    sesion_id: str,
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[
        ServicioNotificaciones,
        Depends(obtener_servicio_notificaciones),
    ],
) -> dict[str, str]:
    servicio.reenviar(sesion_id, convocatoria_id, sesion)
    return {"estado": "evento_programado"}
