import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.modules.notifications.dependencies import construir_despachador
from app.modules.notifications.procesador import ProcesadorOutbox
from app.modules.participations.service import ServicioParticipaciones
from app.modules.sessions.service import ServicioSesiones

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("inter_nos.worker")


def ejecutar_con_sesion(nombre: str, funcion) -> None:
    with SessionLocal() as db:
        try:
            resultado = funcion(db)
            logger.info("%s: procesados=%s", nombre, resultado)
        except Exception:
            db.rollback()
            logger.exception("%s: ejecucion fallida", nombre)


def procesar_outbox(db: Session) -> int:
    procesador = ProcesadorOutbox(db, construir_despachador())
    return procesador.procesar_lote(limite=50)


def expirar_participaciones(db: Session) -> int:
    return ServicioParticipaciones(db).expirar_vencidas()


def cerrar_sesiones(db: Session) -> int:
    return ServicioSesiones(db).cerrar_sesiones_vencidas()


def main() -> None:
    load_dotenv()
    config = obtener_configuracion()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        ejecutar_con_sesion,
        "interval",
        seconds=config.outbox_intervalo_seg,
        args=("outbox", procesar_outbox),
        id="outbox",
        max_instances=1,
    )
    scheduler.add_job(
        ejecutar_con_sesion,
        "interval",
        seconds=config.worker_intervalo_expiracion_seg,
        args=("expiracion", expirar_participaciones),
        id="expiracion",
        max_instances=1,
    )
    scheduler.add_job(
        ejecutar_con_sesion,
        "interval",
        seconds=config.worker_intervalo_cierre_seg,
        args=("cierre-sesiones", cerrar_sesiones),
        id="cierre-sesiones",
        max_instances=1,
    )
    logger.info("Worker iniciado")
    scheduler.start()


if __name__ == "__main__":
    main()
