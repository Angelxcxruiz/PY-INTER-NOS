from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import bloquear_filas_omitiendo_bloqueadas
from app.modules.auth.models import Usuario
from app.modules.sessions.models import Convocatoria, EspacioAcademico, Sesion


class RepositorioSesiones:
    def __init__(self, db: Session) -> None:
        self.db = db

    def espacio_por_id(self, espacio_id: str) -> EspacioAcademico | None:
        return self.db.get(EspacioAcademico, espacio_id)

    def espacio_por_nombre(self, docente_id: str, nombre: str) -> EspacioAcademico | None:
        return self.db.scalar(
            select(EspacioAcademico).where(
                EspacioAcademico.docente_id == docente_id,
                EspacioAcademico.nombre == nombre,
            )
        )

    def agregar(self, entidad) -> None:
        self.db.add(entidad)
        self.db.flush()

    def sesion_por_id(self, sesion_id: str) -> Sesion | None:
        return self.db.get(Sesion, sesion_id)

    def sesion_bloqueada(self, sesion_id: str) -> Sesion | None:
        return self.db.scalar(select(Sesion).where(Sesion.id == sesion_id).with_for_update())

    def listar_sesiones(
        self,
        docente_id: str | None,
        estado: str | None,
        limite: int,
        desplazamiento: int,
    ) -> list[Sesion]:
        stmt = select(Sesion).order_by(Sesion.creada_en.desc())
        if docente_id is not None:
            stmt = stmt.where(Sesion.docente_id == docente_id)
        if estado is not None:
            stmt = stmt.where(Sesion.estado == estado)
        stmt = stmt.offset(desplazamiento).limit(limite)
        return list(self.db.scalars(stmt).all())

    def usuario_por_correo(self, correo: str) -> Usuario | None:
        return self.db.scalar(select(Usuario).where(Usuario.correo == correo.lower()))

    def convocatoria_por_usuario(
        self,
        sesion_id: str,
        usuario_id: str,
    ) -> Convocatoria | None:
        return self.db.scalar(
            select(Convocatoria).where(
                Convocatoria.sesion_id == sesion_id,
                Convocatoria.estudiante_id == usuario_id,
            )
        )

    def convocatoria_por_id(self, convocatoria_id: str) -> Convocatoria | None:
        return self.db.get(Convocatoria, convocatoria_id)

    def convocatorias_sesion(self, sesion_id: str) -> list[Convocatoria]:
        return list(
            self.db.scalars(
                select(Convocatoria)
                .where(Convocatoria.sesion_id == sesion_id)
                .order_by(Convocatoria.creada_en)
            ).all()
        )

    def sesiones_vencidas(self, limite_cierre) -> list[Sesion]:
        stmt = select(Sesion).where(
            Sesion.estado.in_(["SIN_INICIAR", "EN_CURSO"]),
            Sesion.fin_programado < limite_cierre,
        )
        return list(self.db.scalars(bloquear_filas_omitiendo_bloqueadas(stmt, self.db)).all())
