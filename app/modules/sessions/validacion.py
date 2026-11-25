import hmac
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import obtener_configuracion
from app.core.exceptions import NoAutenticado
from app.core.security import normalizar_codigo
from app.modules.auth.models import Usuario
from app.modules.sessions.models import Convocatoria, Sesion

MENSAJE_CREDENCIAL_INVALIDA = "Correo o codigo de convocatoria invalido"


def stub_validador(
    respuesta: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> Callable[[str, str], dict[str, Any]]:
    def validar(correo: str, codigo: str) -> dict[str, Any]:
        del correo, codigo
        if error is not None:
            raise error
        if respuesta is not None:
            return respuesta
        raise NoAutenticado(MENSAJE_CREDENCIAL_INVALIDA)

    return validar


def validador_convocatoria_por_defecto(
    db: Session,
) -> Callable[[str, str], dict[str, Any]]:
    def validar(correo: str, codigo: str) -> dict[str, Any]:
        correo_normalizado = correo.strip().lower()
        usuario = db.scalar(select(Usuario).where(Usuario.correo == correo_normalizado))
        if usuario is None or usuario.rol != "ESTUDIANTE" or not usuario.activo:
            raise NoAutenticado(MENSAJE_CREDENCIAL_INVALIDA)

        codigo_normalizado = normalizar_codigo(codigo)
        if not codigo_normalizado:
            raise NoAutenticado(MENSAJE_CREDENCIAL_INVALIDA)

        convocatorias = list(
            db.scalars(
                select(Convocatoria)
                .where(
                    Convocatoria.estudiante_id == usuario.id,
                    Convocatoria.codigo_vigente.is_(True),
                )
                .with_for_update()
            ).all()
        )

        convocatoria_coincidente = None
        from app.core.security import hash_codigo

        hash_calculado = hash_codigo(codigo_normalizado)
        for convocatoria in convocatorias:
            if convocatoria.codigo_hash is not None and hmac.compare_digest(
                hash_calculado, convocatoria.codigo_hash
            ):
                convocatoria_coincidente = convocatoria
                break

        if convocatoria_coincidente is None:
            raise NoAutenticado(MENSAJE_CREDENCIAL_INVALIDA)

        if obtener_configuracion().exigir_correo_verificado and not usuario.correo_verificado:
            raise NoAutenticado(
                "debes verificar tu correo antes de ingresar; revisa el enlace que enviamos "
                "a tu bandeja de entrada"
            )
        if usuario.estado_cuenta == "SIN_VERIFICAR":
            raise NoAutenticado(
                "Verifica tu correo con el código de 6 dígitos del registro antes de ingresar"
            )

        sesion = db.get(Sesion, convocatoria_coincidente.sesion_id)
        if sesion is None:
            raise NoAutenticado(MENSAJE_CREDENCIAL_INVALIDA)
        if sesion.estado == "SIN_INICIAR":
            raise NoAutenticado("la sesion aun no ha sido iniciada por el docente")
        if sesion.estado == "FINALIZADO":
            raise NoAutenticado("la sesion ya finalizo")

        return {
            "convocatoria_id": convocatoria_coincidente.id,
            "sesion_id": sesion.id,
            "caso_id": sesion.caso_id,
            "estudiante_id": usuario.id,
            "valido": True,
        }

    return validar
