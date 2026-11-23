import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet

from app.core.config import obtener_configuracion

_hasher = PasswordHasher()
configuracion = obtener_configuracion()
_fernet = Fernet(configuracion.fernet_key.encode("utf-8"))


def hash_contrasena(contrasena: str) -> str:
    return _hasher.hash(contrasena)


def verificar_contrasena(hash_guardado: str | None, contrasena: str | None) -> bool:
    """True solo si la contraseña corresponde al hash. Nunca lanza por datos inválidos.

    El orden (hash, contraseña) es el mismo de argon2-cffi. Un hash nulo, vacío, corrupto o que
    no sea Argon2 cuenta como contraseña incorrecta, para que el login responda 401 y no 500.
    """
    if not hash_guardado or contrasena is None:
        return False
    try:
        return _hasher.verify(hash_guardado, contrasena)
    except (VerificationError, InvalidHashError):
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


def generar_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Sin normalizar: el token distingue mayúsculas y minúsculas.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalizar_codigo(codigo: str) -> str:
    sin_espacios = "".join(codigo.upper().replace("-", "").split())
    reemplazos = str.maketrans({"O": "0", "I": "1", "L": "1"})
    return sin_espacios.translate(reemplazos)


def hash_codigo(codigo: str) -> str:
    codigo_normalizado = normalizar_codigo(codigo)
    return hashlib.sha256(codigo_normalizado.encode("utf-8")).hexdigest()


def comparar_hash_codigo(codigo: str, hash_guardado: str) -> bool:
    hash_calculado = hash_codigo(codigo)
    return hmac.compare_digest(hash_calculado, hash_guardado)
