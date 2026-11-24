from typing import Annotated

from fastapi import Depends, Header

from app.core.exceptions import ErrorAutenticacion, ErrorPermiso
from app.core.security import verificar_jwt

MENSAJE_CUENTA_EN_REVISION = (
    "Tu cuenta está en revisión: un administrador debe aprobarla antes de que puedas "
    "usar esta función."
)


def obtener_sesion_basica(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Valida el token sin mirar el estado de la cuenta (para /auth/me y similares)."""
    if not authorization:
        raise ErrorAutenticacion("Token de acceso requerido")
    esquema, separador, token = authorization.partition(" ")
    if separador != " " or esquema.lower() != "bearer" or not token:
        raise ErrorAutenticacion("Token de acceso invalido")
    try:
        return verificar_jwt(token)
    except Exception as exc:
        raise ErrorAutenticacion("Token de acceso invalido") from exc


def obtener_sesion(
    sesion: Annotated[dict, Depends(obtener_sesion_basica)],
) -> dict:
    """Sesión para los endpoints de negocio: un docente pendiente no pasa de aquí."""
    estado = sesion.get("estado_cuenta", "ACTIVO")
    if sesion.get("rol") == "DOCENTE" and estado != "ACTIVO":
        raise ErrorPermiso(MENSAJE_CUENTA_EN_REVISION, detalles={"estado_cuenta": estado})
    return sesion


def requerir_rol(*roles: str):
    def dependencia(sesion: Annotated[dict, Depends(obtener_sesion)]) -> dict:
        if sesion.get("rol") not in roles:
            raise ErrorPermiso("No tiene permisos para realizar esta accion")
        return sesion

    return dependencia


def requerir_permiso(codigo: str):
    def dependencia(sesion: Annotated[dict, Depends(obtener_sesion)]) -> dict:
        permisos = sesion.get("permisos", [])
        if codigo not in permisos:
            raise ErrorAutenticacion("Permiso requerido")
        return sesion

    return dependencia
