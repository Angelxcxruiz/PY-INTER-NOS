from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.exceptions import ErrorConflicto, ErrorNoEncontrado, ErrorPermiso
from app.modules.notifications.repository import RepositorioNotificaciones
from app.modules.sessions.events import publicar
from app.modules.sessions.service import ServicioSesiones


class ServicioNotificaciones:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repositorio = RepositorioNotificaciones(db)
        self.sesiones = ServicioSesiones(db)

    def listar(
        self,
        sesion: dict,
        no_leidas: bool,
        limite: int,
        desplazamiento: int,
    ):
        return self.repositorio.listar(
            sesion["sub"],
            no_leidas,
            limite,
            desplazamiento,
        )

    def contador(self, sesion: dict) -> int:
        return self.repositorio.contador_no_leidas(sesion["sub"])

    def marcar_leida(self, notificacion_id: str, sesion: dict):
        notificacion = self.repositorio.por_id(notificacion_id)
        if notificacion is None:
            raise ErrorNoEncontrado("Notificacion no encontrada")
        if notificacion.usuario_id != sesion["sub"]:
            raise ErrorPermiso("No puede leer notificaciones ajenas")
        if notificacion.leida_en is None:
            notificacion.leida_en = ahora()
            self.db.commit()
        return notificacion

    def marcar_todas_leidas(self, sesion: dict) -> int:
        filas = self.repositorio.listar(
            sesion["sub"],
            True,
            100000,
            0,
        )
        momento = ahora()
        for notificacion in filas:
            notificacion.leida_en = momento
        self.db.commit()
        return len(filas)

    def entregas_sesion(self, sesion_id: str, sesion: dict):
        self.sesiones.obtener(sesion_id, sesion)
        convocatoria_ids = [
            convocatoria.id
            for convocatoria in self.sesiones.listar_convocatorias(
                sesion_id,
                sesion,
            )
        ]
        evento_ids = []
        from sqlalchemy import select

        from app.modules.notifications.models import EventoOutbox

        for evento in self.db.scalars(
            select(EventoOutbox).where(
                EventoOutbox.tipo == "CONVOCATORIA_CREADA",
            )
        ).all():
            if evento.payload.get("convocatoria_id") in convocatoria_ids:
                evento_ids.append(evento.id)
        return self.repositorio.entregas_sesion(evento_ids)

    def reenviar(
        self,
        sesion_id: str,
        convocatoria_id: str,
        sesion: dict,
    ) -> None:
        modelo = self.sesiones.obtener(sesion_id, sesion)
        convocatoria = self.sesiones.obtener_convocatoria_para_participacion(convocatoria_id)
        if convocatoria.sesion_id != modelo.id:
            raise ErrorNoEncontrado("Convocatoria no encontrada")
        if not convocatoria.codigo_vigente:
            raise ErrorConflicto("La convocatoria esta revocada")
        if modelo.estado == "FINALIZADO":
            raise ErrorConflicto("La sesion ya finalizo")
        publicar(
            self.db,
            "CONVOCATORIA_CREADA",
            "convocatoria",
            convocatoria_id,
            {
                "convocatoria_id": convocatoria_id,
                "sesion_id": sesion_id,
                "reenvio_manual": True,
            },
        )
        self.db.commit()


def despachar_outbox(limite: int = 20) -> int:
    """Procesa el outbox en este mismo proceso, tras responder al usuario.

    Evita depender del worker para correos urgentes (como el código de registro). El outbox
    sigue siendo la fuente de verdad: si algo falla aquí, el worker lo reintenta con backoff.
    Nunca lanza: corre en segundo plano y no debe afectar la respuesta ya enviada.
    """
    import logging

    from app.core.config import obtener_configuracion

    if not obtener_configuracion().despacho_inmediato:
        return 0
    # Importaciones locales: evitan un ciclo con los observadores (que usan el módulo de auth).
    from app.core.database import SessionLocal
    from app.modules.notifications.dependencies import construir_despachador
    from app.modules.notifications.procesador import ProcesadorOutbox

    try:
        with SessionLocal() as db:
            return ProcesadorOutbox(db, construir_despachador()).procesar_lote(limite)
    except Exception:
        logging.getLogger(__name__).exception("despacho inmediato del outbox fallido")
        return 0
