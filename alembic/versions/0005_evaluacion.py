"""Crear tablas de evaluacion y retroalimentacion.

Revision ID: 0005_evaluacion
Revises: 0004_participaciones
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0005_evaluacion"
down_revision: str | Sequence[str] | None = "0004_participaciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calificacion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("participacion_id", CHAR(36), nullable=True),
        sa.Column("convocatoria_id", CHAR(36), nullable=True),
        sa.Column("nota_final", sa.Numeric(5, 2), nullable=False),
        sa.Column("puntaje_detalle", sa.JSON(), nullable=False),
        sa.Column("es_ausencia", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("es_parcial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calculada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["participacion_id"],
            ["participacion.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("participacion_id", name="uq_calificacion_participacion"),
        sa.UniqueConstraint("convocatoria_id", name="uq_calificacion_convocatoria"),
        sa.CheckConstraint(
            "(participacion_id IS NOT NULL AND convocatoria_id IS NULL) "
            "OR (participacion_id IS NULL AND convocatoria_id IS NOT NULL)",
            name="ck_calificacion_objetivo",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "retroalimentacion_pregunta",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("calificacion_id", CHAR(36), nullable=False),
        sa.Column("pregunta_id", CHAR(36), nullable=False),
        sa.Column("opcion_elegida_id", CHAR(36), nullable=True),
        sa.Column("es_correcta", sa.Boolean(), nullable=False),
        sa.Column("justificacion", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["calificacion_id"],
            ["calificacion.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["pregunta_id"], ["pregunta.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["opcion_elegida_id"],
            ["opcion.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "calificacion_id",
            "pregunta_id",
            name="uq_retroalimentacion_calificacion_pregunta",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "retroalimentacion_docente",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("participacion_id", CHAR(36), nullable=True),
        sa.Column("convocatoria_id", CHAR(36), nullable=True),
        sa.Column("docente_id", CHAR(36), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.Column("actualizada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["participacion_id"],
            ["participacion.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["docente_id"], ["usuario.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "participacion_id",
            name="uq_retro_docente_participacion",
        ),
        sa.UniqueConstraint(
            "convocatoria_id",
            name="uq_retro_docente_convocatoria",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("retroalimentacion_docente")
    op.drop_table("retroalimentacion_pregunta")
    op.drop_table("calificacion")
