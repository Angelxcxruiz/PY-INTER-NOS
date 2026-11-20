from datetime import UTC, datetime
from typing import Protocol


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
