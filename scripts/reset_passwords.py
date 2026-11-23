"""Reescribe las contraseñas del administrador y de los docentes semilla y comprueba que sirven.

Uso (una línea):
    python scripts/reset_passwords.py

Lee de la configuración (.env), sin imprimirlas:
    - administrador: ADMIN_INICIAL_CORREO / ADMIN_INICIAL_CONTRASENA
    - docentes:      docente1@ y docente2@ <DOMINIO_INSTITUCIONAL> con DOCENTE_PASSWORD
                     (si no está definida, el mismo valor por defecto que usa seed.py)
Solo actualiza usuarios que ya existen; no crea ninguno.
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

from app.core.clock import ahora  # noqa: E402
from app.core.config import obtener_configuracion  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_contrasena, verificar_contrasena  # noqa: E402
from app.modules.auth.models import Usuario  # noqa: E402


def main() -> int:
    config = obtener_configuracion()
    if not config.admin_inicial_correo or not config.admin_inicial_contrasena:
        print("Error: defina ADMIN_INICIAL_CORREO y ADMIN_INICIAL_CONTRASENA", file=sys.stderr)
        return 2

    docente_clave = os.getenv("DOCENTE_PASSWORD", "DocenteInterNos123!")
    objetivo = {
        config.admin_inicial_correo.lower(): config.admin_inicial_contrasena,
        f"docente1@{config.dominio_institucional}".lower(): docente_clave,
        f"docente2@{config.dominio_institucional}".lower(): docente_clave,
    }

    with SessionLocal() as db:
        for correo, clave in objetivo.items():
            usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))
            if usuario is not None:
                usuario.hash_contrasena = hash_contrasena(clave)
                usuario.actualizado_en = ahora()
        db.commit()

    fallos = 0
    with SessionLocal() as db:  # sesión nueva: lee lo que realmente quedó guardado
        for correo, clave in objetivo.items():
            usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))
            if usuario is None:
                print(f"NO EXISTE  {correo}")
                fallos += 1
                continue
            sirve = verificar_contrasena(usuario.hash_contrasena, clave)
            largo = len(usuario.hash_contrasena or "")
            print(f"{'OK     ' if sirve else 'FALLA  '}  {correo}  (hash de {largo} caracteres)")
            fallos += 0 if sirve else 1
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
