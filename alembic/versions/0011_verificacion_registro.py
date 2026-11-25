"""Verificación del correo por código de 6 dígitos al registrarse (Fase 11b).

Revision ID: 0011_verificacion_registro
Revises: 0010_registro
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0011_verificacion_registro"
down_revision: str | Sequence[str] | None = "0010_registro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "codigo_registro",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("usuario_id", CHAR(36), nullable=False),
        # Hash con clave del servidor; nulo hasta que se genera el código al armar el correo.
        sa.Column("codigo_hash", CHAR(64), nullable=True),
        sa.Column("expira_en", DATETIME(fsp=6), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usado_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_codigo_registro_usuario_id", "codigo_registro", ["usuario_id"])
    op.create_index("ix_codigo_registro_codigo_hash", "codigo_registro", ["codigo_hash"])

    # El estado nuevo SIN_VERIFICAR entra en la restricción; los usuarios existentes siguen ACTIVO.
    op.drop_constraint("ck_usuario_estado_cuenta", "usuario", type_="check")
    op.create_check_constraint(
        "ck_usuario_estado_cuenta",
        "usuario",
        "estado_cuenta IN ('SIN_VERIFICAR', 'ACTIVO', 'PENDIENTE', 'RECHAZADO')",
    )


def downgrade() -> None:
    # Quien no había verificado su correo vuelve a PENDIENTE (sin acceso hasta que se revise).
    op.execute(
        "UPDATE usuario SET estado_cuenta = 'PENDIENTE' WHERE estado_cuenta = 'SIN_VERIFICAR'"
    )
    op.drop_constraint("ck_usuario_estado_cuenta", "usuario", type_="check")
    op.create_check_constraint(
        "ck_usuario_estado_cuenta",
        "usuario",
        "estado_cuenta IN ('ACTIVO', 'PENDIENTE', 'RECHAZADO')",
    )
    # drop_table elimina también sus índices (uno de ellos lo exige la clave foránea).
    op.drop_table("codigo_registro")
