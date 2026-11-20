from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import obtener_configuracion
from app.core.database import Base
import app.modules.auth.models  # noqa: F401
import app.modules.cases.models  # noqa: F401
import app.modules.sessions.models  # noqa: F401

configuracion_alembic = context.config
configuracion = obtener_configuracion()

if configuracion_alembic.config_file_name is not None:
    fileConfig(configuracion_alembic.config_file_name)

configuracion_alembic.set_main_option("sqlalchemy.url", configuracion.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=configuracion.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        configuracion_alembic.get_section(
            configuracion_alembic.config_ini_section
        ) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
