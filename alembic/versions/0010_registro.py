"""Registro de usuarios con aprobación de docentes (Fase 11).

Revision ID: 0010_registro
Revises: 0008_restablecer_contrasena
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0010_registro"
down_revision: str | Sequence[str] | None = "0008_restablecer_contrasena"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Default ACTIVO: nadie de los que ya existen queda bloqueado.
    op.add_column(
        "usuario",
        sa.Column("estado_cuenta", sa.String(20), nullable=False, server_default="ACTIVO"),
    )
    op.add_column("usuario", sa.Column("aprobado_en", DATETIME(fsp=6), nullable=True))
    op.add_column("usuario", sa.Column("aprobado_por_id", CHAR(36), nullable=True))
    op.add_column("usuario", sa.Column("motivo_rechazo", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_usuario_aprobado_por",
        "usuario",
        "usuario",
        ["aprobado_por_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_usuario_estado_cuenta", "usuario", ["estado_cuenta"])
    op.create_check_constraint(
        "ck_usuario_estado_cuenta",
        "usuario",
        "estado_cuenta IN ('ACTIVO', 'PENDIENTE', 'RECHAZADO')",
    )
    op.execute("UPDATE usuario SET estado_cuenta = 'ACTIVO'")


def downgrade() -> None:
    op.drop_constraint("ck_usuario_estado_cuenta", "usuario", type_="check")
    op.drop_index("ix_usuario_estado_cuenta", table_name="usuario")
    op.drop_constraint("fk_usuario_aprobado_por", "usuario", type_="foreignkey")
    op.drop_column("usuario", "motivo_rechazo")
    op.drop_column("usuario", "aprobado_por_id")
    op.drop_column("usuario", "aprobado_en")
    op.drop_column("usuario", "estado_cuenta")
