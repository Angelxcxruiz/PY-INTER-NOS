import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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
    correo_verificado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    verificado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    # Fase 11: ACTIVO | PENDIENTE | RECHAZADO. Los usuarios previos quedan ACTIVO.
    estado_cuenta: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVO", server_default="ACTIVO", index=True
    )
    aprobado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    aprobado_por_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)

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


class VerificacionCorreo(Base):
    """Solicitud de verificación del correo de un usuario.

    La fila se reserva al solicitar (dentro de la transacción de negocio, con el mismo id que
    viaja en el evento) pero el token se genera después, al construir el correo. Solo se guarda
    su hash SHA-256: el token en claro no se puede recuperar.
    """

    __tablename__ = "verificacion_correo"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    usada_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class CodigoRegistro(Base):
    """Código de 6 dígitos para verificar el correo al registrarse (Fase 11b).

    Igual que la verificación de correo de la Fase 9: la fila se reserva en la transacción del
    registro (su id viaja en el evento) y el código se genera después, al construir el correo.
    En la base solo queda su hash con clave (HMAC); el código en claro no se puede recuperar.
    Hay una sola fila por usuario: pedir un código nuevo reemplaza la anterior.
    """

    __tablename__ = "codigo_registro"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nulo hasta que el observador genera el código al construir el correo.
    codigo_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True, index=True)
    expira_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    usado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class TokenCorreo(Base):
    """Enlace de un solo uso para restablecer la contraseña.

    Se guarda el hash SHA-256 para validar y el token cifrado con Fernet para poder
    construir el correo desde el worker, igual que los códigos de convocatoria.
    """

    __tablename__ = "token_correo"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=uuid_como_texto)
    usuario_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposito: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    token_cifrado: Mapped[str] = mapped_column(String(512), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
