from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import bloquear_filas_omitiendo_bloqueadas
from app.modules.participations.models import (
    AutorizacionRepeticion,
    Participacion,
    Respuesta,
)


class RepositorioParticipaciones:
    def __init__(self, db: Session) -> None:
        self.db = db

    def por_id(self, participacion_id: str) -> Participacion | None:
        return self.db.get(Participacion, participacion_id)

    def por_id_bloqueada(self, participacion_id: str) -> Participacion | None:
        return self.db.scalar(
            select(Participacion).where(Participacion.id == participacion_id).with_for_update()
        )

    def en_progreso_convocatoria(
        self,
        convocatoria_id: str,
    ) -> Participacion | None:
        return self.db.scalar(
            select(Participacion)
            .where(
                Participacion.convocatoria_id == convocatoria_id,
                Participacion.estado == "EN_PROGRESO",
            )
            .order_by(Participacion.numero_intento.desc())
            .limit(1)
        )

    def vigentes_convocatoria(self, convocatoria_id: str) -> list[Participacion]:
        return list(
            self.db.scalars(
                select(Participacion)
                .where(Participacion.convocatoria_id == convocatoria_id)
                .order_by(Participacion.numero_intento.desc())
            ).all()
        )

    def agregar(self, entidad) -> None:
        self.db.add(entidad)
        self.db.flush()

    def respuesta(
        self,
        participacion_id: str,
        pregunta_id: str,
    ) -> Respuesta | None:
        return self.db.scalar(
            select(Respuesta).where(
                Respuesta.participacion_id == participacion_id,
                Respuesta.pregunta_id == pregunta_id,
            )
        )

    def respuestas(self, participacion_id: str) -> list[Respuesta]:
        return list(
            self.db.scalars(
                select(Respuesta).where(Respuesta.participacion_id == participacion_id)
            ).all()
        )

    def autorizacion_no_usada(
        self,
        convocatoria_id: str,
    ) -> AutorizacionRepeticion | None:
        return self.db.scalar(
            select(AutorizacionRepeticion)
            .where(
                AutorizacionRepeticion.convocatoria_id == convocatoria_id,
                AutorizacionRepeticion.usada_en.is_(None),
            )
            .order_by(AutorizacionRepeticion.creada_en.desc())
        )

    def autorizaciones_convocatoria(
        self,
        convocatoria_id: str,
    ) -> list[AutorizacionRepeticion]:
        return list(
            self.db.scalars(
                select(AutorizacionRepeticion)
                .where(
                    AutorizacionRepeticion.convocatoria_id == convocatoria_id,
                )
                .order_by(AutorizacionRepeticion.creada_en.desc())
            ).all()
        )

    def vencidas(self, ahora) -> list[Participacion]:
        consulta = select(Participacion).where(
            Participacion.estado == "EN_PROGRESO",
            Participacion.vence_en <= ahora,
        )
        return list(self.db.scalars(bloquear_filas_omitiendo_bloqueadas(consulta, self.db)).all())

    def abiertas_por_sesion(self, convocatoria_ids: list[str]) -> list[Participacion]:
        if not convocatoria_ids:
            return []
        return list(
            self.db.scalars(
                select(Participacion).where(
                    Participacion.convocatoria_id.in_(convocatoria_ids),
                    Participacion.estado == "EN_PROGRESO",
                )
            ).all()
        )
