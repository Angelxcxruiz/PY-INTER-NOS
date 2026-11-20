"""Crear tablas de gestion de casos academicos.

Revision ID: 0002_casos
Revises: 0001_auth
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0002_casos"
down_revision: str | Sequence[str] | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "caso",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("docente_creador_id", CHAR(36), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("desarrollo_situacional", sa.Text(), nullable=False),
        sa.Column("contexto_historia", sa.Text(), nullable=False),
        sa.Column("tiempo_estimado_min", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="BORRADOR"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("caso_origen_id", CHAR(36), nullable=True),
        sa.Column("publicado_en", DATETIME(fsp=6), nullable=True),
        sa.Column("archivado_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.Column("actualizado_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["docente_creador_id"],
            ["usuario.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["caso_origen_id"],
            ["caso.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_caso_docente_estado", "caso", ["docente_creador_id", "estado"])
    op.create_index("ix_caso_estado_publicado", "caso", ["estado", "publicado_en"])

    op.create_table(
        "escenario",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("caso_id", CHAR(36), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("contexto", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["caso_id"], ["caso.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("caso_id", "orden", name="uq_escenario_caso_orden"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_escenario_caso_id", "escenario", ["caso_id"])

    op.create_table(
        "pregunta",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("escenario_id", CHAR(36), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["escenario_id"], ["escenario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escenario_id", "orden", name="uq_pregunta_escenario_orden"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_pregunta_escenario_id", "pregunta", ["escenario_id"])

    op.create_table(
        "opcion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("pregunta_id", CHAR(36), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("es_correcta", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("justificacion", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["pregunta_id"], ["pregunta.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pregunta_id", "orden", name="uq_opcion_pregunta_orden"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_opcion_pregunta_id", "opcion", ["pregunta_id"])

    op.create_table(
        "rubrica",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("caso_id", CHAR(36), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("escala_min", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
        sa.Column("escala_max", sa.Numeric(5, 2), nullable=False, server_default="5.00"),
        sa.Column("nota_aprobatoria", sa.Numeric(5, 2), nullable=False, server_default="3.00"),
        sa.Column("publicada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.Column("actualizada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["caso_id"], ["caso.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("caso_id", name="uq_rubrica_caso"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )

    op.create_table(
        "criterio_rubrica",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("rubrica_id", CHAR(36), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("peso", sa.Numeric(5, 2), nullable=False),
        sa.ForeignKeyConstraint(["rubrica_id"], ["rubrica.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index(
        "ix_criterio_rubrica_rubrica_id",
        "criterio_rubrica",
        ["rubrica_id"],
    )

    op.create_table(
        "criterio_pregunta",
        sa.Column("criterio_id", CHAR(36), nullable=False),
        sa.Column("pregunta_id", CHAR(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["criterio_id"],
            ["criterio_rubrica.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pregunta_id"],
            ["pregunta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("criterio_id", "pregunta_id"),
        sa.UniqueConstraint(
            "criterio_id",
            "pregunta_id",
            name="uq_criterio_pregunta",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )


def downgrade() -> None:
    op.drop_table("criterio_pregunta")
    op.drop_index("ix_criterio_rubrica_rubrica_id", table_name="criterio_rubrica")
    op.drop_table("criterio_rubrica")
    op.drop_table("rubrica")
    op.drop_index("ix_opcion_pregunta_id", table_name="opcion")
    op.drop_table("opcion")
    op.drop_index("ix_pregunta_escenario_id", table_name="pregunta")
    op.drop_table("pregunta")
    op.drop_index("ix_escenario_caso_id", table_name="escenario")
    op.drop_table("escenario")
    op.drop_index("ix_caso_estado_publicado", table_name="caso")
    op.drop_index("ix_caso_docente_estado", table_name="caso")
    op.drop_table("caso")
