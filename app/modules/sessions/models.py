import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class EspacioAcademico(Base):
    __tablename__ = "espacio_academico"
    __table_args__ = (UniqueConstraint("docente_id", "nombre", name="uq_espacio_docente_nombre"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    docente_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class Sesion(Base):
    __tablename__ = "sesion"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    caso_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("caso.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    docente_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    espacio_academico_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("espacio_academico.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inicio_programado: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    fin_programado: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    tiempo_maximo_min: Mapped[int] = mapped_column(Integer, nullable=False)
    lugar_fisico: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mensaje_personalizado: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SIN_INICIAR",
        index=True,
    )
    iniciada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    finalizada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    finalizada_por: Mapped[str | None] = mapped_column(String(20), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    convocatorias: Mapped[list["Convocatoria"]] = relationship(
        back_populates="sesion",
        cascade="all, delete-orphan",
    )


class Convocatoria(Base):
    __tablename__ = "convocatoria"
    __table_args__ = (UniqueConstraint("sesion_id", "estudiante_id", name="uq_sesion_estudiante"),)

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    sesion_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("sesion.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    estudiante_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    codigo_cifrado: Mapped[str | None] = mapped_column(String(512), nullable=True)
    codigo_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    codigo_vigente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    revocada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    sesion: Mapped[Sesion] = relationship(back_populates="convocatorias")
