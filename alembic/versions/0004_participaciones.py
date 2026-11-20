"""Crear tablas de participaciones.

Revision ID: 0004_participaciones
Revises: 0003_sesiones
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0004_participaciones"
down_revision: str | Sequence[str] | None = "0003_sesiones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "participacion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("convocatoria_id", CHAR(36), nullable=False),
        sa.Column("numero_intento", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("iniciada_en", DATETIME(fsp=6), nullable=False),
        sa.Column("vence_en", DATETIME(fsp=6), nullable=False),
        sa.Column("finalizada_en", DATETIME(fsp=6), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False, server_default="EN_PROGRESO"),
        sa.Column("motivo_cierre", sa.String(60), nullable=True),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "convocatoria_id",
            "numero_intento",
            name="uq_participacion_convocatoria_intento",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_participacion_estado", "participacion", ["estado"])
    op.create_index(
        "ix_participacion_convocatoria_id",
        "participacion",
        ["convocatoria_id"],
    )

    op.create_table(
        "respuesta",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("participacion_id", CHAR(36), nullable=False),
        sa.Column("pregunta_id", CHAR(36), nullable=False),
        sa.Column("opcion_id", CHAR(36), nullable=False),
        sa.Column("respondida_en", DATETIME(fsp=6), nullable=False),
        sa.Column("actualizada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["participacion_id"],
            ["participacion.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pregunta_id"],
            ["pregunta.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opcion_id"],
            ["opcion.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "participacion_id",
            "pregunta_id",
            name="uq_respuesta_participacion_pregunta",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_respuesta_participacion_id", "respuesta", ["participacion_id"])

    op.create_table(
        "autorizacion_repeticion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("convocatoria_id", CHAR(36), nullable=False),
        sa.Column("docente_id", CHAR(36), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.Column("usada_en", DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["docente_id"],
            ["usuario.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_autorizacion_repeticion_convocatoria_id",
        "autorizacion_repeticion",
        ["convocatoria_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_autorizacion_repeticion_convocatoria_id",
        table_name="autorizacion_repeticion",
    )
    op.drop_table("autorizacion_repeticion")
    op.drop_index("ix_respuesta_participacion_id", table_name="respuesta")
    op.drop_table("respuesta")
    op.drop_index("ix_participacion_convocatoria_id", table_name="participacion")
    op.drop_index("ix_participacion_estado", table_name="participacion")
    op.drop_table("participacion")
