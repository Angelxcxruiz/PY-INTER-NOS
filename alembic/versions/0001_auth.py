"""Crear tablas de autenticacion y usuarios.

Revision ID: 0001_auth
Revises:
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME as MYSQL_DATETIME

revision: str = "0001_auth"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("correo", sa.String(length=255), nullable=False),
        sa.Column("hash_contrasena", sa.String(length=255), nullable=True),
        sa.Column("rol", sa.String(length=30), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("creado_en", MYSQL_DATETIME(fsp=6), nullable=False),
        sa.Column("actualizado_en", MYSQL_DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("correo", name="uq_usuario_correo"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_usuario_rol_activo", "usuario", ["rol", "activo"])

    op.create_table(
        "permiso",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("codigo", sa.String(length=100), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo", name="uq_permiso_codigo"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "usuario_permiso",
        sa.Column("usuario_id", CHAR(36), nullable=False),
        sa.Column("permiso_id", CHAR(36), nullable=False),
        sa.Column("asignado_en", MYSQL_DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permiso_id"],
            ["permiso.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("usuario_id", "permiso_id"),
        sa.UniqueConstraint(
            "usuario_id",
            "permiso_id",
            name="uq_usuario_permiso",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_usuario_permiso_permiso_id",
        "usuario_permiso",
        ["permiso_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_usuario_permiso_permiso_id",
        table_name="usuario_permiso",
    )
    op.drop_table("usuario_permiso")
    op.drop_table("permiso")
    op.drop_index("ix_usuario_rol_activo", table_name="usuario")
    op.drop_table("usuario")
