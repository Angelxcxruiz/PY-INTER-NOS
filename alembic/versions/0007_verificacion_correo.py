"""Verificacion de correo del estudiante.

Revision ID: 0007_verificacion_correo
Revises: 0006_notificaciones
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0007_verificacion_correo"
down_revision: str | Sequence[str] | None = "0006_notificaciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("correo_verificado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("usuario", sa.Column("verificado_en", DATETIME(fsp=6), nullable=True))

    # Quienes ya existen como administrador o docente no deben quedar bloqueados.
    op.execute(
        "UPDATE usuario SET correo_verificado = 1, verificado_en = UTC_TIMESTAMP(6) "
        "WHERE rol IN ('ADMINISTRADOR', 'DOCENTE')"
    )

    op.create_table(
        "verificacion_correo",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("usuario_id", CHAR(36), nullable=False),
        # Nulo hasta que el observador genera el token al construir el correo.
        sa.Column("token_hash", CHAR(64), nullable=True),
        sa.Column("expira_en", DATETIME(fsp=6), nullable=False),
        sa.Column("usada_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_verificacion_correo_token_hash"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("verificacion_correo")
    op.drop_column("usuario", "verificado_en")
    op.drop_column("usuario", "correo_verificado")
