"""Crear tablas de sesiones y convocatorias.

Revision ID: 0003_sesiones
Revises: 0002_casos
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0003_sesiones"
down_revision: str | Sequence[str] | None = "0002_casos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "espacio_academico",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=True),
        sa.Column("docente_id", CHAR(36), nullable=False),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["docente_id"], ["usuario.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("docente_id", "nombre", name="uq_espacio_docente_nombre"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "sesion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("caso_id", CHAR(36), nullable=False),
        sa.Column("docente_id", CHAR(36), nullable=False),
        sa.Column("espacio_academico_id", CHAR(36), nullable=False),
        sa.Column("inicio_programado", DATETIME(fsp=6), nullable=False),
        sa.Column("fin_programado", DATETIME(fsp=6), nullable=False),
        sa.Column("tiempo_maximo_min", sa.Integer(), nullable=False),
        sa.Column("lugar_fisico", sa.String(300), nullable=True),
        sa.Column("mensaje_personalizado", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="SIN_INICIAR"),
        sa.Column("iniciada_en", DATETIME(fsp=6), nullable=True),
        sa.Column("finalizada_en", DATETIME(fsp=6), nullable=True),
        sa.Column("finalizada_por", sa.String(20), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["caso_id"], ["caso.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["docente_id"], ["usuario.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["espacio_academico_id"],
            ["espacio_academico.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_sesion_estado", "sesion", ["estado"])
    op.create_index("ix_sesion_docente_id", "sesion", ["docente_id"])

    op.create_table(
        "convocatoria",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("sesion_id", CHAR(36), nullable=False),
        sa.Column("estudiante_id", CHAR(36), nullable=False),
        sa.Column("codigo_cifrado", sa.String(512), nullable=True),
        sa.Column("codigo_hash", sa.String(64), nullable=True),
        sa.Column("codigo_vigente", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revocada_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["sesion_id"], ["sesion.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["estudiante_id"], ["usuario.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sesion_id", "estudiante_id", name="uq_sesion_estudiante"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_convocatoria_sesion_id", "convocatoria", ["sesion_id"])
    op.create_index("ix_convocatoria_estudiante_id", "convocatoria", ["estudiante_id"])
    op.create_index("ix_convocatoria_codigo_hash", "convocatoria", ["codigo_hash"])


def downgrade() -> None:
    op.drop_index("ix_convocatoria_codigo_hash", table_name="convocatoria")
    op.drop_index("ix_convocatoria_estudiante_id", table_name="convocatoria")
    op.drop_index("ix_convocatoria_sesion_id", table_name="convocatoria")
    op.drop_table("convocatoria")
    op.drop_index("ix_sesion_docente_id", table_name="sesion")
    op.drop_index("ix_sesion_estado", table_name="sesion")
    op.drop_table("sesion")
    op.drop_table("espacio_academico")
