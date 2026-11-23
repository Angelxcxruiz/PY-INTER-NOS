"""Regenera los códigos de convocatoria que la FERNET_KEY actual ya no puede descifrar.

Uso:
    python scripts/rotar_codigos.py            # regenera y muestra los códigos nuevos
    python scripts/rotar_codigos.py --simular  # solo lista las afectadas, no cambia nada

Cuando se cambia FERNET_KEY, los `codigo_cifrado` guardados con la clave anterior quedan
ilegibles (la validación del login sigue funcionando porque usa `codigo_hash`, pero «Ver
código» y el correo de invitación fallan). Este script, contra la base del .env:

  1. busca las convocatorias con codigo_vigente = 1 cuyo codigo_cifrado no se puede descifrar;
  2. genera un código nuevo para cada una, lo cifra y recalcula su hash;
  3. IMPRIME los códigos nuevos UNA sola vez, junto con el correo del estudiante.

No envía ningún correo. El script no vuelve a mostrar los códigos (el docente puede verlos
después en el panel con «Ver código»); cópielos de esta salida para reenviarlos.
"""

import argparse
import sys

from cryptography.fernet import InvalidToken
from dotenv import load_dotenv
from sqlalchemy import select

load_dotenv()

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import (  # noqa: E402
    cifrar,
    descifrar,
    generar_codigo,
    hash_codigo,
)
from app.modules.auth.models import Usuario  # noqa: E402
from app.modules.cases.models import Caso  # noqa: E402,F401  (resuelve claves foráneas)
from app.modules.sessions.models import Convocatoria, Sesion  # noqa: E402


def es_ilegible(codigo_cifrado: str | None) -> bool:
    if not codigo_cifrado:
        return True
    try:
        descifrar(codigo_cifrado)
    except (InvalidToken, ValueError):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenera códigos de convocatoria ilegibles")
    parser.add_argument("--simular", action="store_true", help="solo lista, no modifica nada")
    argumentos = parser.parse_args()

    with SessionLocal() as db:
        filas = db.execute(
            select(Convocatoria, Usuario, Sesion)
            .join(Usuario, Usuario.id == Convocatoria.estudiante_id)
            .join(Sesion, Sesion.id == Convocatoria.sesion_id)
            .where(Convocatoria.codigo_vigente.is_(True))
            .order_by(Sesion.creada_en, Usuario.correo)
        ).all()
        afectadas = [fila for fila in filas if es_ilegible(fila[0].codigo_cifrado)]

        print(f"Convocatorias vigentes: {len(filas)} | con codigo ilegible: {len(afectadas)}")
        if not afectadas:
            print("Nada que regenerar.")
            return 0

        if argumentos.simular:
            for _, estudiante, sesion in afectadas:
                print(f"  (simulacion) {estudiante.correo}  sesion {sesion.estado}")
            print("Simulacion: no se modifico nada.")
            return 0

        nuevos = []
        for convocatoria, estudiante, sesion in afectadas:
            codigo = generar_codigo(8)
            convocatoria.codigo_cifrado = cifrar(codigo)
            convocatoria.codigo_hash = hash_codigo(codigo)
            nuevos.append((estudiante.correo, estudiante.nombre, sesion.estado, codigo))
        db.commit()

    # Comprobación con una sesión nueva: lo guardado debe descifrarse y coincidir con su hash.
    with SessionLocal() as db:
        for correo, _nombre, _estado, codigo in nuevos:
            convocatoria = db.scalar(
                select(Convocatoria)
                .join(Usuario, Usuario.id == Convocatoria.estudiante_id)
                .where(Usuario.correo == correo, Convocatoria.codigo_hash == hash_codigo(codigo))
            )
            if convocatoria is None or descifrar(convocatoria.codigo_cifrado) != codigo:
                print(f"ERROR: no se pudo verificar el codigo de {correo}", file=sys.stderr)
                return 1

    print("\n" + "=" * 72)
    print("CODIGOS NUEVOS - se muestran UNA SOLA VEZ. Copielos ahora para reenviarlos.")
    print("(El script no los vuelve a mostrar; el docente los ve en «Ver codigo».)")
    print("=" * 72)
    for correo, nombre, estado, codigo in nuevos:
        print(f"{correo:<36} {nombre:<20} sesion {estado:<12} {codigo}")
    print("=" * 72)
    print(f"{len(nuevos)} codigo(s) regenerado(s) y verificados. No se envio ningun correo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
