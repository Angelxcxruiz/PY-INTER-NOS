import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class Participacion(Base):
    __tablename__ = "participacion"
    __table_args__ = (
        UniqueConstraint(
            "convocatoria_id",
            "numero_intento",
            name="uq_participacion_convocatoria_intento",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    convocatoria_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("convocatoria.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero_intento: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    iniciada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    vence_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    finalizada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="EN_PROGRESO",
        index=True,
    )
    motivo_cierre: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Respuesta(Base):
    __tablename__ = "respuesta"
    __table_args__ = (
        UniqueConstraint(
            "participacion_id",
            "pregunta_id",
            name="uq_respuesta_participacion_pregunta",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    participacion_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("participacion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pregunta_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("pregunta.id", ondelete="CASCADE"),
        nullable=False,
    )
    opcion_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("opcion.id", ondelete="CASCADE"),
        nullable=False,
    )
    respondida_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class AutorizacionRepeticion(Base):
    __tablename__ = "autorizacion_repeticion"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    convocatoria_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("convocatoria.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    docente_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    usada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
