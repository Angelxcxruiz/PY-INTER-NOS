import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR, DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class EventoOutbox(Base):
    __tablename__ = "evento_outbox"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    clave_idempotencia: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    tipo: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    agregado_tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    agregado_id: Mapped[str] = mapped_column(CHAR(36), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        index=True,
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proximo_intento_en: Mapped[datetime | None] = mapped_column(
        DATETIME(fsp=6),
        nullable=True,
        index=True,
    )
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    procesado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)


class Notificacion(Base):
    __tablename__ = "notificacion"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "evento_id",
            "tipo",
            name="uq_notificacion_usuario_evento_tipo",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    leida_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    evento_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("evento_outbox.id", ondelete="CASCADE"),
        nullable=False,
    )
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class EntregaCorreo(Base):
    __tablename__ = "entrega_correo"
    __table_args__ = (
        UniqueConstraint(
            "evento_id",
            "destinatario",
            "tipo",
            name="uq_entrega_evento_destinatario_tipo",
        ),
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    evento_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("evento_outbox.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    destinatario: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDIENTE",
        index=True,
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enviado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
