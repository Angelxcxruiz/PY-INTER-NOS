"""Composición visual de escenarios y registro de archivos subidos (Fase 14).

`composicion_escenario`: una composición por escenario (UNIQUE), con las capas en JSON para
poder editarla de nuevo. `archivo_adjunto`: cada archivo subido por un docente, para poder
borrarlo y, más adelante, migrarlo a S3.

Revision ID: 0014_composiciones
Revises: 0013_puzzles
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0014_composiciones"
down_revision: str | Sequence[str] | None = "0013_puzzles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archivo_adjunto",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("docente_id", CHAR(36), nullable=False),
        sa.Column("nombre_original", sa.String(255), nullable=False),
        sa.Column("tipo_mime", sa.String(50), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("ruta_almacenamiento", sa.String(255), nullable=False),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["docente_id"], ["usuario.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("ruta_almacenamiento", name="uq_archivo_adjunto_ruta"),
    )
    op.create_index("ix_archivo_adjunto_docente_id", "archivo_adjunto", ["docente_id"])

    op.create_table(
        "composicion_escenario",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("escenario_id", CHAR(36), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False),
        sa.Column("alto", sa.Integer(), nullable=False),
        sa.Column("fondo_color", sa.String(7), nullable=False),
        sa.Column("capas", sa.JSON(), nullable=False),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.Column("actualizado_en", DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["escenario_id"], ["escenario.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("escenario_id", name="uq_composicion_escenario_escenario_id"),
    )


def downgrade() -> None:
    # Al borrar la tabla se van también sus índices y claves foráneas.
    op.drop_table("composicion_escenario")
    op.drop_table("archivo_adjunto")
