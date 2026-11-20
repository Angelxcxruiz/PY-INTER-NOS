from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evaluations.models import (
    Calificacion,
    RetroalimentacionDocente,
    RetroalimentacionPregunta,
)


class RepositorioEvaluaciones:
    def __init__(self, db: Session) -> None:
        self.db = db

    def por_participacion(self, participacion_id: str) -> Calificacion | None:
        return self.db.scalar(
            select(Calificacion).where(Calificacion.participacion_id == participacion_id)
        )

    def por_convocatoria_ausencia(self, convocatoria_id: str) -> Calificacion | None:
        return self.db.scalar(
            select(Calificacion).where(
                Calificacion.convocatoria_id == convocatoria_id,
                Calificacion.es_ausencia.is_(True),
            )
        )

    def agregar(self, entidad) -> None:
        self.db.add(entidad)
        self.db.flush()

    def retroalimentacion_por_participacion(
        self,
        participacion_id: str,
    ) -> RetroalimentacionDocente | None:
        return self.db.scalar(
            select(RetroalimentacionDocente).where(
                RetroalimentacionDocente.participacion_id == participacion_id
            )
        )

    def retroalimentacion_por_convocatoria(
        self,
        convocatoria_id: str,
    ) -> RetroalimentacionDocente | None:
        return self.db.scalar(
            select(RetroalimentacionDocente).where(
                RetroalimentacionDocente.convocatoria_id == convocatoria_id
            )
        )

    def retroalimentaciones_sesion(
        self,
        convocatoria_ids: list[str],
        participacion_ids: list[str],
    ) -> list[RetroalimentacionDocente]:
        stmt = select(RetroalimentacionDocente)
        criterios = []
        if convocatoria_ids:
            criterios.append(RetroalimentacionDocente.convocatoria_id.in_(convocatoria_ids))
        if participacion_ids:
            criterios.append(RetroalimentacionDocente.participacion_id.in_(participacion_ids))
        if criterios:
            from sqlalchemy import or_

            stmt = stmt.where(or_(*criterios))
        else:
            return []
        return list(self.db.scalars(stmt).all())

    def retroalimentaciones_pregunta(
        self,
        calificacion_id: str,
    ) -> list[RetroalimentacionPregunta]:
        return list(
            self.db.scalars(
                select(RetroalimentacionPregunta).where(
                    RetroalimentacionPregunta.calificacion_id == calificacion_id
                )
            ).all()
        )
