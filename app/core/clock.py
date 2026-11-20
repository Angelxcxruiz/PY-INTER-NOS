from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Reloj(Protocol):
    def ahora(self) -> datetime: ...


class RelojSistema:
    def ahora(self) -> datetime:
        return datetime.now(UTC)


reloj_predeterminado = RelojSistema()


def ahora(reloj: Reloj | None = None) -> datetime:
    reloj_activo = reloj or reloj_predeterminado
    instante = reloj_activo.ahora()
    if instante.tzinfo is None:
        return instante.replace(tzinfo=UTC)
    return instante.astimezone(UTC)


def mostrar_bogota(instante: datetime) -> str:
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=UTC)
    bogota = instante.astimezone(ZoneInfo("America/Bogota"))
    return bogota.strftime("%d/%m/%Y %H:%M")
