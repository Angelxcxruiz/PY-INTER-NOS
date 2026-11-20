from typing import Any


class ErrorDominio(Exception):
    codigo: str = "ERROR_DOMINIO"
    estado_http: int = 400

    def __init__(
        self,
        mensaje: str,
        *,
        codigo: str | None = None,
        detalles: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo or self.codigo
        self.detalles = detalles or {}


class ErrorValidacion(ErrorDominio):
    codigo = "VALIDACION_FALLIDA"
    estado_http = 422


class ErrorNoEncontrado(ErrorDominio):
    codigo = "NO_ENCONTRADO"
    estado_http = 404


class ErrorPermiso(ErrorDominio):
    codigo = "PERMISO_DENEGADO"
    estado_http = 403


class ErrorConflicto(ErrorDominio):
    codigo = "CONFLICTO"
    estado_http = 409


class ErrorAutenticacion(ErrorDominio):
    codigo = "NO_AUTENTICADO"
    estado_http = 401
