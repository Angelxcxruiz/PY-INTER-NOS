import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import CHAR, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class ArchivoAdjunto(Base):
    """Registro de cada archivo subido: permite borrarlo y migrarlo a S3 después."""

    __tablename__ = "archivo_adjunto"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    docente_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(50), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    ruta_almacenamiento: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    origen: Mapped[str] = mapped_column(
        String(12), nullable=False, default="SUBIDO", server_default="SUBIDO"
    )
    prompt_generacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
