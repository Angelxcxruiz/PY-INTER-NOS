import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from app.core.config import obtener_configuracion

_hasher = PasswordHasher()
configuracion = obtener_configuracion()
_fernet = Fernet(configuracion.fernet_key.encode("utf-8"))


def hash_contrasena(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, contrasena)
    except VerifyMismatchError:
        return False


def crear_jwt(datos: dict[str, Any], expiracion_minutos: int | None = None) -> str:
    minutos = expiracion_minutos or configuracion.jwt_expira_min
    expiracion = datetime.now(UTC) + timedelta(minutes=minutos)
    payload = {**datos, "exp": expiracion}
    return jwt.encode(payload, configuracion.jwt_secreto, algorithm="HS256")


def verificar_jwt(token: str) -> dict[str, Any]:
    return jwt.decode(token, configuracion.jwt_secreto, algorithms=["HS256"])


def cifrar(valor: str) -> str:
    return _fernet.encrypt(valor.encode("utf-8")).decode("ascii")


def descifrar(valor_cifrado: str) -> str:
    return _fernet.decrypt(valor_cifrado.encode("ascii")).decode("utf-8")


def generar_codigo(longitud: int = 8) -> str:
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(caracteres) for _ in range(longitud))
