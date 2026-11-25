"""Origen de los archivos (subido o generado con IA) y prompt de generación (Fase 15).

`origen` distingue en la galería lo generado de lo subido; los archivos que ya existían quedan como
SUBIDO. `prompt_generacion` guarda el texto con el que se generó la imagen, para poder ajustarlo y
regenerar.

Revision ID: 0015_origen_archivos
Revises: 0014_composiciones
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_origen_archivos"
down_revision: str | Sequence[str] | None = "0014_composiciones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "archivo_adjunto",
        sa.Column("origen", sa.String(12), nullable=False, server_default="SUBIDO"),
    )
    op.add_column("archivo_adjunto", sa.Column("prompt_generacion", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_archivo_adjunto_origen",
        "archivo_adjunto",
        "origen IN ('SUBIDO', 'GENERADO_IA')",
    )


def downgrade() -> None:
    # La restricción se quita antes que la columna que la usa.
    op.drop_constraint("ck_archivo_adjunto_origen", "archivo_adjunto", type_="check")
    op.drop_column("archivo_adjunto", "prompt_generacion")
    op.drop_column("archivo_adjunto", "origen")
