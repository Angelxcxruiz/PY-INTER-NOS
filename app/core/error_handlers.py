from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import ErrorDominio


def respuesta_error(codigo: str, mensaje: str, detalles: dict | None = None) -> dict:
    return {
        "error": {
            "codigo": codigo,
            "mensaje": mensaje,
            "detalles": detalles or {},
        }
    }


def registrar_manejadores(app: FastAPI) -> None:
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
        detalles = {"errores": exc.errors()}
        return JSONResponse(
            status_code=422,
            content=respuesta_error("VALIDACION_FALLIDA", "Datos invalidos", detalles),
        )
