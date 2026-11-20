import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR, DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class Calificacion(Base):
    __tablename__ = "calificacion"
    __table_args__ = (
        CheckConstraint(
            "(participacion_id IS NOT NULL AND convocatoria_id IS NULL) "
            "OR (participacion_id IS NULL AND convocatoria_id IS NOT NULL)",
            name="ck_calificacion_objetivo",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    participacion_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("participacion.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    convocatoria_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("convocatoria.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    nota_final: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    puntaje_detalle: Mapped[dict] = mapped_column(JSON, nullable=False)
    es_ausencia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    es_parcial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calculada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class RetroalimentacionPregunta(Base):
    __tablename__ = "retroalimentacion_pregunta"
    __table_args__ = (
        UniqueConstraint(
            "calificacion_id",
            "pregunta_id",
            name="uq_retroalimentacion_calificacion_pregunta",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    calificacion_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("calificacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    pregunta_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("pregunta.id", ondelete="CASCADE"),
        nullable=False,
    )
    opcion_elegida_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("opcion.id", ondelete="SET NULL"),
        nullable=True,
    )
    es_correcta: Mapped[bool] = mapped_column(Boolean, nullable=False)
    justificacion: Mapped[str] = mapped_column(Text, nullable=False)


class RetroalimentacionDocente(Base):
    __tablename__ = "retroalimentacion_docente"
    __table_args__ = (
        UniqueConstraint("participacion_id", name="uq_retro_docente_participacion"),
        UniqueConstraint("convocatoria_id", name="uq_retro_docente_convocatoria"),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    participacion_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("participacion.id", ondelete="CASCADE"),
        nullable=True,
    )
    convocatoria_id: Mapped[str | None] = mapped_column(
        CHAR(36),
        ForeignKey("convocatoria.id", ondelete="CASCADE"),
        nullable=True,
    )
    docente_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
