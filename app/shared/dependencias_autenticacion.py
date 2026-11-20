from typing import Annotated

from fastapi import Depends, Header

from app.core.exceptions import ErrorAutenticacion, ErrorPermiso
from app.core.security import verificar_jwt


def obtener_sesion(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    if not authorization:
        raise ErrorAutenticacion("Token de acceso requerido")
    esquema, separador, token = authorization.partition(" ")
    if separador != " " or esquema.lower() != "bearer" or not token:
        raise ErrorAutenticacion("Token de acceso invalido")
    try:
        return verificar_jwt(token)
    except Exception as exc:
        raise ErrorAutenticacion("Token de acceso invalido") from exc


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
