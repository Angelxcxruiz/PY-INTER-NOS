from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import ErrorDominio

# SQLSTATE 45000 con SIGNAL: es el error que lanzan los triggers de la base (migración 0012).
CODIGO_MYSQL_REGLA_DE_TRIGGER = 1644


def respuesta_error(codigo: str, mensaje: str, detalles: dict | None = None) -> dict:
    return {
        "error": {
            "codigo": codigo,
            "mensaje": mensaje,
            "detalles": detalles or {},
        }
    }


def _errores_serializables(errores: list) -> list:
    """Un validador que lanza ValueError deja la excepción en `ctx`, que no es JSON."""
    return jsonable_encoder(
        [
            {**error, "ctx": {clave: str(valor) for clave, valor in error["ctx"].items()}}
            if "ctx" in error
            else error
            for error in errores
        ]
    )


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(DBAPIError)
    async def manejar_error_de_base(request: Request, exc: DBAPIError) -> JSONResponse:
        """Traduce la regla de un trigger a un 409 claro; cualquier otro error sigue siendo 500."""
        del request
        argumentos = getattr(exc.orig, "args", ())
        if len(argumentos) >= 2 and argumentos[0] == CODIGO_MYSQL_REGLA_DE_TRIGGER:
            return JSONResponse(
                status_code=409,
                content=respuesta_error("REGLA_DE_BASE_DE_DATOS", str(argumentos[1])),
            )
        return JSONResponse(
            status_code=500,
            content=respuesta_error("ERROR_INTERNO", "Ocurrió un error inesperado"),
        )

    @app.exception_handler(ErrorDominio)
    async def manejar_error_dominio(
        request: Request,
        exc: ErrorDominio,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.estado_http,
            content=respuesta_error(exc.codigo, exc.mensaje, exc.detalles),
        )

    @app.exception_handler(RequestValidationError)
    async def manejar_validacion(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        detalles = {"errores": _errores_serializables(exc.errors())}
        return JSONResponse(
            status_code=422,
            content=respuesta_error("VALIDACION_FALLIDA", "Datos invalidos", detalles),
        )
