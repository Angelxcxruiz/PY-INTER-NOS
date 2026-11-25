import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import CHAR, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class Caso(Base):
    __tablename__ = "caso"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    docente_creador_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    desarrollo_situacional: Mapped[str] = mapped_column(Text, nullable=False)
    contexto_historia: Mapped[str] = mapped_column(Text, nullable=False)
    tiempo_estimado_min: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="BORRADOR")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    caso_origen_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("caso.id", ondelete="SET NULL"),
        nullable=True,
    )
    publicado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    archivado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    escenarios: Mapped[list["Escenario"]] = relationship(
        back_populates="caso",
        cascade="all, delete-orphan",
        order_by="Escenario.orden",
    )
    rubrica: Mapped["Rubrica | None"] = relationship(
        back_populates="caso",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Escenario(Base):
    __tablename__ = "escenario"
    __table_args__ = (UniqueConstraint("caso_id", "orden", name="uq_escenario_caso_orden"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    caso_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("caso.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    contexto: Mapped[str] = mapped_column(Text, nullable=False)

    caso: Mapped[Caso] = relationship(back_populates="escenarios")
    preguntas: Mapped[list["Pregunta"]] = relationship(
        back_populates="escenario",
        cascade="all, delete-orphan",
        order_by="Pregunta.orden",
    )
    puzzles: Mapped[list["Puzzle"]] = relationship(
        back_populates="escenario",
        cascade="all, delete-orphan",
        order_by="Puzzle.orden",
    )
    composicion: Mapped["ComposicionEscenario | None"] = relationship(
        back_populates="escenario",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ComposicionEscenario(Base):
    """Composición visual del escenario (editor visual): capas guardadas como JSON editable."""

    __tablename__ = "composicion_escenario"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    escenario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("escenario.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    ancho: Mapped[int] = mapped_column(Integer, nullable=False)
    alto: Mapped[int] = mapped_column(Integer, nullable=False)
    fondo_color: Mapped[str] = mapped_column(String(7), nullable=False)
    capas: Mapped[list] = mapped_column(JSON, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    escenario: Mapped[Escenario] = relationship(back_populates="composicion")


class Puzzle(Base):
    """Puzzle lógico previo a las preguntas de un escenario. No puntúa."""

    __tablename__ = "puzzle"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    escenario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("escenario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)
    contenido: Mapped[dict] = mapped_column(JSON, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    escenario: Mapped[Escenario] = relationship(back_populates="puzzles")


class Pregunta(Base):
    __tablename__ = "pregunta"
    __table_args__ = (
        UniqueConstraint("escenario_id", "orden", name="uq_pregunta_escenario_orden"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    escenario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("escenario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    enunciado: Mapped[str] = mapped_column(Text, nullable=False)

    escenario: Mapped[Escenario] = relationship(back_populates="preguntas")
    opciones: Mapped[list["Opcion"]] = relationship(
        back_populates="pregunta",
        cascade="all, delete-orphan",
        order_by="Opcion.orden",
    )


class Opcion(Base):
    __tablename__ = "opcion"
    __table_args__ = (UniqueConstraint("pregunta_id", "orden", name="uq_opcion_pregunta_orden"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    pregunta_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("pregunta.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    es_correcta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    justificacion: Mapped[str] = mapped_column(Text, nullable=False)

    pregunta: Mapped[Pregunta] = relationship(back_populates="opciones")


class Rubrica(Base):
    __tablename__ = "rubrica"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    caso_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("caso.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    escala_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    escala_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("5.00")
    )
    nota_aprobatoria: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("3.00"),
    )
    publicada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    caso: Mapped[Caso] = relationship(back_populates="rubrica")
    criterios: Mapped[list["CriterioRubrica"]] = relationship(
        back_populates="rubrica",
        cascade="all, delete-orphan",
        order_by="CriterioRubrica.orden",
    )


class CriterioRubrica(Base):
    __tablename__ = "criterio_rubrica"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    rubrica_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("rubrica.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    peso: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    rubrica: Mapped[Rubrica] = relationship(back_populates="criterios")
    preguntas: Mapped[list[Pregunta]] = relationship(
        secondary="criterio_pregunta",
        lazy="select",
    )

    @property
    def pregunta_ids(self) -> list[str]:
        return [pregunta.id for pregunta in self.preguntas]


class CriterioPregunta(Base):
    __tablename__ = "criterio_pregunta"
    __table_args__ = (UniqueConstraint("criterio_id", "pregunta_id", name="uq_criterio_pregunta"),)

    criterio_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("criterio_rubrica.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pregunta_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("pregunta.id", ondelete="CASCADE"),
        primary_key=True,
    )
