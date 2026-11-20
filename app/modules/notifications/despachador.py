from collections import defaultdict

from sqlalchemy.orm import Session

from app.modules.notifications.observadores import Observador


class DespachadorEventos:
    def __init__(self) -> None:
        self._suscriptores: dict[str, list[Observador]] = defaultdict(list)

    def suscribir(self, tipo: str, observador: Observador) -> None:
        self._suscriptores[tipo].append(observador)

    def despachar(self, db: Session, evento) -> None:
        for observador in self._suscriptores.get(evento.tipo, []):
            observador.manejar(db, evento)
