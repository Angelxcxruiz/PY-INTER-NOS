from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.cases.models import (
    Caso,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Puzzle,
    Rubrica,
)


def carga_caso_completa():
    return (
        selectinload(Caso.escenarios)
        .selectinload(Escenario.preguntas)
        .selectinload(Pregunta.opciones),
        selectinload(Caso.escenarios).selectinload(Escenario.puzzles),
        selectinload(Caso.rubrica)
        .selectinload(Rubrica.criterios)
        .selectinload(CriterioRubrica.preguntas),
    )


class RepositorioCasos:
    def __init__(self, db: Session) -> None:
        self.db = db

    def por_id(self, caso_id: str) -> Caso | None:
        opciones_carga = carga_caso_completa()
        stmt = select(Caso).where(Caso.id == caso_id)
        for carga in opciones_carga:
            stmt = stmt.options(carga)
        return self.db.scalar(stmt)

    def listar(
        self,
        usuario_id: str | None,
        estado: str | None,
        limite: int,
        desplazamiento: int,
    ) -> list[Caso]:
        stmt = select(Caso)
        if usuario_id is not None:
            stmt = stmt.where(Caso.docente_creador_id == usuario_id)
        if estado is not None:
            stmt = stmt.where(Caso.estado == estado)
        stmt = stmt.order_by(Caso.actualizado_en.desc()).offset(desplazamiento).limit(limite)
        for carga in carga_caso_completa():
            stmt = stmt.options(carga)
        return list(self.db.scalars(stmt).unique().all())

    def publicados(self, limite: int, desplazamiento: int) -> list[Caso]:
        stmt = (
            select(Caso)
            .where(Caso.estado == "PUBLICADO")
            .order_by(Caso.publicado_en.desc())
            .offset(desplazamiento)
            .limit(limite)
        )
        for carga in carga_caso_completa():
            stmt = stmt.options(carga)
        return list(self.db.scalars(stmt).unique().all())

    def agregar(self, caso: Caso) -> Caso:
        self.db.add(caso)
        self.db.flush()
        return caso

    def registrar(self, entidad) -> None:
        self.db.add(entidad)
        self.db.flush()

    def eliminar_caso(self, caso: Caso) -> None:
        self.db.delete(caso)

    def escenario_por_id(self, escenario_id: str) -> Escenario | None:
        return self.db.get(Escenario, escenario_id)

    def pregunta_por_id(self, pregunta_id: str) -> Pregunta | None:
        return self.db.get(Pregunta, pregunta_id)

    def opcion_por_id(self, opcion_id: str) -> Opcion | None:
        return self.db.get(Opcion, opcion_id)

    def puzzle_por_id(self, puzzle_id: str) -> Puzzle | None:
        return self.db.get(Puzzle, puzzle_id)

    def obtener_rubrica(self, caso_id: str) -> Rubrica | None:
        stmt = (
            select(Rubrica)
            .where(Rubrica.caso_id == caso_id)
            .options(selectinload(Rubrica.criterios).selectinload(CriterioRubrica.preguntas))
        )
        return self.db.scalar(stmt)

    def quitar_rubrica(self, rubrica: Rubrica) -> None:
        self.db.delete(rubrica)
        self.db.flush()
