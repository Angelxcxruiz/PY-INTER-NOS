"""MariaDB anterior a 10.6 (XAMPP) no admite SKIP LOCKED: el outbox no debe romperse."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql

from app.core.database import bloquear_filas_omitiendo_bloqueadas
from app.modules.notifications.models import EventoOutbox


def _sql(version, mariadb: bool) -> str:
    dialecto = SimpleNamespace(server_version_info=version, is_mariadb=mariadb)
    db = SimpleNamespace(connection=lambda: SimpleNamespace(dialect=dialecto))
    consulta = bloquear_filas_omitiendo_bloqueadas(select(EventoOutbox), db)
    return str(consulta.compile(dialect=mysql.dialect()))


@pytest.mark.parametrize(
    ("version", "mariadb", "con_skip_locked"),
    [
        ((8, 0, 36), False, True),  # MySQL 8
        ((10, 4, 32), True, False),  # MariaDB de XAMPP
        ((10, 6, 0), True, True),  # MariaDB que ya lo soporta
    ],
)
def test_skip_locked_solo_donde_existe(version, mariadb, con_skip_locked) -> None:
    sql = _sql(version, mariadb)

    assert "FOR UPDATE" in sql
    assert ("SKIP LOCKED" in sql) is con_skip_locked
