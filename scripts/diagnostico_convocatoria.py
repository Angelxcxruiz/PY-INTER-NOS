"""Diagnóstico de convocatorias contra la base real (solo lectura).

Uso:
    python scripts/diagnostico_convocatoria.py
    python scripts/diagnostico_convocatoria.py <convocatoria_id>

Usa el mismo DATABASE_URL que la API (variable de entorno o .env), así que muestra
exactamente lo que ve el servidor.
"""

import argparse
import sys

from dotenv import load_dotenv
from sqlalchemy import func, select, text

load_dotenv()

# Se importan todos los modelos para que SQLAlchemy resuelva las claves foráneas.
import app.modules.auth.models  # noqa: E402,F401
import app.modules.cases.models  # noqa: E402,F401
import app.modules.sessions.models  # noqa: E402,F401
from app.core.database import SessionLocal, engine  # noqa: E402
from app.modules.auth.models import Usuario  # noqa: E402
from app.modules.sessions.models import Convocatoria, Sesion  # noqa: E402


def revisar_id(db, valor: str) -> None:
    limpio = valor.strip().strip("\"'{}")
    print("\n== Revision del id recibido ==")
    print(f"recibido        : {valor!r}")
    print(f"longitud        : {len(valor)} (un UUID tiene 36)")
    if limpio != valor:
        print(f"AVISO: tiene espacios, comillas o llaves. Limpio queda: {limpio!r}")
    if "{{" in valor or "}}" in valor:
        print("AVISO: parece una variable de Postman SIN resolver.")

    exacta = db.get(Convocatoria, valor)
    print(f"existe como convocatoria.id (busqueda exacta, la que usa la API): {exacta is not None}")
    if exacta is None and limpio != valor:
        print(f"existe tras limpiarlo: {db.get(Convocatoria, limpio) is not None}")

    como_sesion = db.get(Sesion, limpio)
    if como_sesion is not None:
        print(f"ATENCION: es un SESION.id (estado {como_sesion.estado}), no una convocatoria.")
    como_usuario = db.get(Usuario, limpio)
    if como_usuario is not None:
        print(f"ATENCION: ese valor es un USUARIO.id ({como_usuario.correo}), no una convocatoria.")
    if exacta is None and como_sesion is None and como_usuario is None:
        print("No coincide con ninguna convocatoria, sesion ni usuario de esta base.")

    if exacta is not None:
        sesion = db.get(Sesion, exacta.sesion_id)
        estudiante = db.get(Usuario, exacta.estudiante_id)
        print(f"-> sesion_id={exacta.sesion_id} estado={sesion.estado if sesion else None}")
        print(
            f"-> estudiante={estudiante.correo if estudiante else None} "
            f"vigente={exacta.codigo_vigente}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostico de convocatorias")
    parser.add_argument("convocatoria_id", nargs="?", help="id a comprobar")
    args = parser.parse_args()

    print("== Base de datos a la que se conecta ==")
    print(engine.url.render_as_string(hide_password=True))

    with SessionLocal() as db:
        try:
            version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception as exc:
            version = f"no se pudo leer ({type(exc).__name__})"
        print(f"revision alembic: {version}")

        total = db.scalar(select(func.count()).select_from(Convocatoria))
        print(f"\n== Convocatorias (total: {total}) ==")
        filas = db.execute(
            select(
                Convocatoria.id,
                Convocatoria.sesion_id,
                Usuario.correo,
                Convocatoria.codigo_vigente,
                Sesion.estado,
            )
            .join(Sesion, Sesion.id == Convocatoria.sesion_id)
            .join(Usuario, Usuario.id == Convocatoria.estudiante_id)
            .order_by(Convocatoria.creada_en)
        ).all()
        for fila in filas:
            print(
                f"convocatoria_id={fila[0]}  sesion_id={fila[1]}  correo={fila[2]}  "
                f"vigente={bool(fila[3])}  sesion={fila[4]}"
            )
        if not filas:
            print("(ninguna)")

        if args.convocatoria_id is not None:
            revisar_id(db, args.convocatoria_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
