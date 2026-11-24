from collections.abc import Generator

from sqlalchemy import Select, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import obtener_configuracion


class Base(DeclarativeBase):
    pass


configuracion = obtener_configuracion()
engine = create_engine(
    configuracion.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def bloquear_filas_omitiendo_bloqueadas(consulta: Select, db: Session) -> Select:
    """`FOR UPDATE SKIP LOCKED` en MySQL 8; `FOR UPDATE` simple donde no existe.

    MariaDB anterior a 10.6 (p. ej. el de XAMPP) no admite SKIP LOCKED y rompería el outbox.
    """
    dialecto = db.connection().dialect
    version = getattr(dialecto, "server_version_info", None) or (0,)
    sin_soporte = getattr(dialecto, "is_mariadb", False) and tuple(version) < (10, 6)
    return consulta.with_for_update() if sin_soporte else consulta.with_for_update(skip_locked=True)
