"""Crear tablas de notificaciones y eventos.

Revision ID: 0006_notificaciones
Revises: 0005_evaluacion
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import CHAR, DATETIME

revision: str = "0006_notificaciones"
down_revision: str | Sequence[str] | None = "0005_evaluacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evento_outbox",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("clave_idempotencia", sa.String(128), nullable=False),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("agregado_tipo", sa.String(60), nullable=False),
        sa.Column("agregado_id", CHAR(36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="PENDIENTE"),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proximo_intento_en", DATETIME(fsp=6), nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("creado_en", DATETIME(fsp=6), nullable=False),
        sa.Column("procesado_en", DATETIME(fsp=6), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave_idempotencia", name="uq_evento_clave_idempotencia"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_evento_outbox_tipo", "evento_outbox", ["tipo"])
    op.create_index("ix_evento_outbox_estado", "evento_outbox", ["estado"])
    op.create_index(
        "ix_evento_outbox_proximo_intento_en",
        "evento_outbox",
        ["proximo_intento_en"],
    )

    op.create_table(
        "notificacion",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("usuario_id", CHAR(36), nullable=False),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("leida_en", DATETIME(fsp=6), nullable=True),
        sa.Column("evento_id", CHAR(36), nullable=False),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evento_id"],
            ["evento_outbox.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id",
            "evento_id",
            "tipo",
            name="uq_notificacion_usuario_evento_tipo",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_notificacion_usuario_id", "notificacion", ["usuario_id"])

    op.create_table(
        "entrega_correo",
        sa.Column("id", CHAR(36), nullable=False),
        sa.Column("evento_id", CHAR(36), nullable=False),
        sa.Column("destinatario", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(60), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="PENDIENTE"),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        sa.Column("enviado_en", DATETIME(fsp=6), nullable=True),
        sa.Column("creada_en", DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["evento_id"],
            ["evento_outbox.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evento_id",
            "destinatario",
            "tipo",
            name="uq_entrega_evento_destinatario_tipo",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_entrega_correo_evento_id", "entrega_correo", ["evento_id"])
    op.create_index("ix_entrega_correo_estado", "entrega_correo", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_entrega_correo_estado", table_name="entrega_correo")
    op.drop_index("ix_entrega_correo_evento_id", table_name="entrega_correo")
    op.drop_table("entrega_correo")
    op.drop_index("ix_notificacion_usuario_id", table_name="notificacion")
    op.drop_table("notificacion")
    op.drop_index("ix_evento_outbox_proximo_intento_en", table_name="evento_outbox")
    op.drop_index("ix_evento_outbox_estado", table_name="evento_outbox")
    op.drop_index("ix_evento_outbox_tipo", table_name="evento_outbox")
    op.drop_table("evento_outbox")
