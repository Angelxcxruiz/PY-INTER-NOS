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


class ErrorArchivoDemasiadoGrande(ErrorDominio):
    codigo = "ARCHIVO_DEMASIADO_GRANDE"
    estado_http = 413


class ErrorServicioNoDisponible(ErrorDominio):
    codigo = "SERVICIO_NO_DISPONIBLE"
    estado_http = 503


class ErrorLimiteExcedido(ErrorDominio):
    codigo = "LIMITE_EXCEDIDO"
    estado_http = 429


class ErrorProveedorExterno(ErrorDominio):
    codigo = "PROVEEDOR_EXTERNO_FALLIDO"
    estado_http = 502


class ErrorTiempoAgotado(ErrorDominio):
    codigo = "TIEMPO_AGOTADO"
    estado_http = 504


class ErrorAlmacenamiento(ErrorDominio):
    codigo = "ALMACENAMIENTO_FALLIDO"
    estado_http = 500


class ErrorTipoArchivo(ErrorDominio):
    codigo = "TIPO_ARCHIVO_NO_PERMITIDO"
    estado_http = 415


class ErrorAutenticacion(ErrorDominio):
    codigo = "NO_AUTENTICADO"
    estado_http = 401


class NoAutenticado(ErrorAutenticacion):
    codigo = "NO_AUTENTICADO"
    estado_http = 401
