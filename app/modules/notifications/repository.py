from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.notifications.models import EntregaCorreo, Notificacion


class RepositorioNotificaciones:
    def __init__(self, db: Session) -> None:
        self.db = db

    def listar(
        self,
        usuario_id: str,
        no_leidas: bool,
        limite: int,
        desplazamiento: int,
    ) -> list[Notificacion]:
        stmt = select(Notificacion).where(Notificacion.usuario_id == usuario_id)
        if no_leidas:
            stmt = stmt.where(Notificacion.leida_en.is_(None))
        stmt = stmt.order_by(Notificacion.creada_en.desc()).offset(desplazamiento).limit(limite)
        return list(self.db.scalars(stmt).all())

    def contador_no_leidas(self, usuario_id: str) -> int:
        from sqlalchemy import func

        return (
            self.db.scalar(
                select(func.count(Notificacion.id)).where(
                    Notificacion.usuario_id == usuario_id,
                    Notificacion.leida_en.is_(None),
                )
            )
            or 0
        )

    def por_id(self, notificacion_id: str) -> Notificacion | None:
        return self.db.get(Notificacion, notificacion_id)

    def entregas_sesion(self, evento_ids: list[str]) -> list[EntregaCorreo]:
        if not evento_ids:
            return []
        return list(
            self.db.scalars(
                select(EntregaCorreo)
                .where(EntregaCorreo.evento_id.in_(evento_ids))
                .order_by(EntregaCorreo.creada_en.desc())
            ).all()
        )
