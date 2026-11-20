from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.auth.models import Usuario
from app.modules.cases.models import Caso, Escenario
from app.modules.evaluations.models import (
    Calificacion,
    RetroalimentacionDocente,
    RetroalimentacionPregunta,
)
from app.modules.participations.models import Participacion, Respuesta
from app.modules.sessions.models import Convocatoria, Sesion


class RepositorioReportes:
    def __init__(self, db: Session) -> None:
        self.db = db

    def sesion_por_id(self, sesion_id: str) -> Sesion | None:
        return self.db.get(Sesion, sesion_id)

    def sesiones_caso(self, caso_id: str) -> list[Sesion]:
        return list(self.db.scalars(select(Sesion).where(Sesion.caso_id == caso_id)).all())

    def sesiones_espacio(self, espacio_id: str) -> list[Sesion]:
        return list(
            self.db.scalars(select(Sesion).where(Sesion.espacio_academico_id == espacio_id)).all()
        )

    def caso_por_id(self, caso_id: str) -> Caso | None:
        return self.db.scalar(
            select(Caso)
            .where(Caso.id == caso_id)
            .options(selectinload(Caso.escenarios).selectinload(Escenario.preguntas))
        )

    def convocatorias_sesion(self, sesion_id: str) -> list[Convocatoria]:
        return list(
            self.db.scalars(select(Convocatoria).where(Convocatoria.sesion_id == sesion_id)).all()
        )

    def usuario_por_id(self, usuario_id: str) -> Usuario | None:
        return self.db.get(Usuario, usuario_id)

    def participaciones_convocatoria(
        self,
        convocatoria_id: str,
    ) -> list[Participacion]:
        return list(
            self.db.scalars(
                select(Participacion)
                .where(Participacion.convocatoria_id == convocatoria_id)
                .order_by(Participacion.numero_intento.desc())
            ).all()
        )

    def respuestas_participacion(
        self,
        participacion_id: str,
    ) -> list[Respuesta]:
        return list(
            self.db.scalars(
                select(Respuesta).where(Respuesta.participacion_id == participacion_id)
            ).all()
        )

    def calificacion_participacion(
        self,
        participacion_id: str,
    ) -> Calificacion | None:
        return self.db.scalar(
            select(Calificacion).where(Calificacion.participacion_id == participacion_id)
        )

    def calificacion_ausencia(
        self,
        convocatoria_id: str,
    ) -> Calificacion | None:
        return self.db.scalar(
            select(Calificacion).where(
                Calificacion.convocatoria_id == convocatoria_id,
                Calificacion.es_ausencia.is_(True),
            )
        )

    def retroalimentacion_participacion(
        self,
        participacion_id: str,
    ) -> RetroalimentacionDocente | None:
        return self.db.scalar(
            select(RetroalimentacionDocente).where(
                RetroalimentacionDocente.participacion_id == participacion_id
            )
        )

    def retroalimentacion_convocatoria(
        self,
        convocatoria_id: str,
    ) -> RetroalimentacionDocente | None:
        return self.db.scalar(
            select(RetroalimentacionDocente).where(
                RetroalimentacionDocente.convocatoria_id == convocatoria_id
            )
        )

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
