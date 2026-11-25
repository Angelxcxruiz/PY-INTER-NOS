"""Puzzles lógicos antes de cada escenario (Fase 13).

Un puzzle pertenece a un escenario (0 a 3 por escenario) y NO puntúa. El contenido, con su
solución, va en una columna JSON validada por tipo en la aplicación.

Revision ID: 0013_puzzles
Revises: 0012_triggers_vistas
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0013_puzzles"
down_revision: str | Sequence[str] | None = "0012_triggers_vistas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIPOS = ("ORDENAR_SECUENCIA", "EMPAREJAR_CONCEPTOS", "PIEZA_FALTANTE", "CLASIFICAR")


def upgrade() -> None:
    op.create_table(
        "puzzle",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("escenario_id", CHAR(36), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("contenido", sa.JSON(), nullable=False),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["escenario_id"], ["escenario.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "tipo IN (" + ", ".join(f"'{tipo}'" for tipo in TIPOS) + ")",
            name="ck_puzzle_tipo",
        ),
    )
    op.create_index("ix_puzzle_escenario_id", "puzzle", ["escenario_id"])


def downgrade() -> None:
    op.drop_table("puzzle")
