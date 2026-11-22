"""Tokens para restablecer la contrasena por correo.

Revision ID: 0008_restablecer_contrasena
Revises: 0007_verificacion_correo
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0008_restablecer_contrasena"
down_revision: str | Sequence[str] | None = "0007_verificacion_correo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_correo",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("usuario_id", CHAR(36), nullable=False),
        sa.Column("proposito", sa.String(30), nullable=False),
        sa.Column("token_hash", CHAR(64), nullable=False),
        sa.Column("token_cifrado", sa.String(512), nullable=False),
        sa.Column("expira_en", DATETIME(fsp=6), nullable=False),
        sa.Column("usado_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_token_correo_hash"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("token_correo")
