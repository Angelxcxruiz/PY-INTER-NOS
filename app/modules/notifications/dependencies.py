from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.notifications.adapters import crear_adapter_puerto
from app.modules.notifications.despachador import DespachadorEventos
from app.modules.notifications.observadores import (
    ObservadorCorreo,
    ObservadorNotificacionInterna,
)
from app.modules.notifications.procesador import ProcesadorOutbox
from app.modules.notifications.service import ServicioNotificaciones


def obtener_servicio_notificaciones(
    db: Annotated[Session, Depends(get_db)],
) -> ServicioNotificaciones:
    return ServicioNotificaciones(db)


def construir_despachador() -> DespachadorEventos:
    despachador = DespachadorEventos()
    puerto = crear_adapter_puerto()
    observador_correo = ObservadorCorreo(puerto)
    observador_notificacion = ObservadorNotificacionInterna()
    for tipo in (
        "SESION_INICIADA",
        "SESION_FINALIZADA",
        "RETROALIMENTACION_AGREGADA",
    ):
        despachador.suscribir(tipo, observador_notificacion)
    for tipo in (
        "CONVOCATORIA_CREADA",
        "CALIFICACION_REGISTRADA",
        "SESION_REPROGRAMADA",
    ):
        despachador.suscribir(tipo, observador_correo)
    return despachador


def obtener_procesador(
    db: Annotated[Session, Depends(get_db)],
) -> ProcesadorOutbox:
    return ProcesadorOutbox(db, construir_despachador())
