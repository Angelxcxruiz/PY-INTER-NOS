import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def uuid_como_texto() -> str:
    return str(uuid.uuid4())


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        default=uuid_como_texto,
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    correo: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hash_contrasena: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rol: Mapped[str] = mapped_column(String(30), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)

    permisos: Mapped[list["Permiso"]] = relationship(
        secondary="usuario_permiso",
        back_populates="usuarios",
    )


class Permiso(Base):
    __tablename__ = "permiso"

    id: Mapped[str] = mapped_column(
        CHAR(36),
        primary_key=True,
        default=uuid_como_texto,
    )
    codigo: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)

    usuarios: Mapped[list[Usuario]] = relationship(
        secondary="usuario_permiso",
        back_populates="permisos",
    )


class UsuarioPermiso(Base):
    __tablename__ = "usuario_permiso"
    __table_args__ = (UniqueConstraint("usuario_id", "permiso_id", name="uq_usuario_permiso"),)

    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permiso_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("permiso.id", ondelete="CASCADE"),
        primary_key=True,
    )
    asignado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
