from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.modules.notifications.despachador import DespachadorEventos
from app.modules.notifications.models import EventoOutbox


def calcular_backoff_minutos(intentos: int) -> int:
    if intentos < 1:
        return 1
    return 2 ** max(0, intentos - 1)


class ProcesadorOutbox:
    def __init__(
        self,
        db: Session,
        despachador: DespachadorEventos,
    ) -> None:
        self.db = db
        self.despachador = despachador

    def procesar_lote(self, limite: int = 50) -> int:
        momento = ahora()
        stmt = (
            select(EventoOutbox)
            .where(
                EventoOutbox.estado.in_(["PENDIENTE", "FALLIDO"]),
                (
                    (EventoOutbox.proximo_intento_en.is_(None))
                    | (EventoOutbox.proximo_intento_en <= momento)
                ),
            )
            .order_by(EventoOutbox.creado_en)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        eventos = list(self.db.scalars(stmt).all())
        procesados = 0

        for evento in eventos:
            if evento.estado == "PROCESADO":
                continue
            evento.estado = "PROCESANDO"
            evento.intentos += 1
            self.db.commit()

            try:
                self.despachador.despachar(self.db, evento)
            except Exception as exc:
                max_intentos = obtener_configuracion().outbox_max_intentos
                evento.ultimo_error = str(exc)
                if evento.intentos >= max_intentos:
                    evento.estado = "FALLIDO"
                    evento.proximo_intento_en = None
                else:
                    evento.estado = "PENDIENTE"
                    minutos = calcular_backoff_minutos(evento.intentos)
                    evento.proximo_intento_en = ahora() + timedelta(minutes=minutos)
                self.db.commit()
                continue

            evento.estado = "PROCESADO"
            evento.proximo_intento_en = None
            evento.ultimo_error = None
            evento.procesado_en = ahora()
            self.db.commit()
            procesados += 1

        return procesados
