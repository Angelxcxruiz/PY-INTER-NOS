from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.evaluations.dependencies import obtener_servicio_evaluaciones
from app.modules.evaluations.schemas import (
    EntradaRetroalimentacionDocente,
    ResultadoParticipacionSalida,
    RetroalimentacionDocenteSalida,
)
from app.modules.evaluations.service import ServicioEvaluaciones
from app.modules.sessions.service import ServicioSesiones
from app.shared.dependencias_autenticacion import obtener_sesion

router = APIRouter(tags=["M5 - Evaluacion"])


@router.get(
    "/participations/{participacion_id}/result",
    response_model=ResultadoParticipacionSalida,
)
def resultado_participacion(
    participacion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioEvaluaciones, Depends(obtener_servicio_evaluaciones)],
) -> ResultadoParticipacionSalida:
    return ResultadoParticipacionSalida.model_validate(
        servicio.resultado_participacion(participacion_id, sesion)
    )


@router.get("/convocatorias/{convocatoria_id}/result")
def resultado_convocatoria(
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioEvaluaciones, Depends(obtener_servicio_evaluaciones)],
) -> dict:
    return servicio.resultado_convocatoria(convocatoria_id, sesion)


@router.post(
    "/participations/{participacion_id}/retroalimentacion",
    response_model=RetroalimentacionDocenteSalida,
)
def retroalimentar_participacion(
    participacion_id: str,
    entrada: EntradaRetroalimentacionDocente,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioEvaluaciones, Depends(obtener_servicio_evaluaciones)],
) -> RetroalimentacionDocenteSalida:
    return RetroalimentacionDocenteSalida.model_validate(
        servicio.guardar_retroalimentacion(
            participacion_id,
            None,
            entrada.texto,
            sesion,
        )
    )


@router.post(
    "/convocatorias/{convocatoria_id}/retroalimentacion",
    response_model=RetroalimentacionDocenteSalida,
)
def retroalimentar_convocatoria(
    convocatoria_id: str,
    entrada: EntradaRetroalimentacionDocente,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioEvaluaciones, Depends(obtener_servicio_evaluaciones)],
) -> RetroalimentacionDocenteSalida:
    return RetroalimentacionDocenteSalida.model_validate(
        servicio.guardar_retroalimentacion(
            None,
            convocatoria_id,
            entrada.texto,
            sesion,
        )
    )


@router.get("/sessions/{sesion_id}/retroalimentaciones")
def listar_retroalimentaciones(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    servicio_sesiones = ServicioSesiones(db)
    modelo = servicio_sesiones.obtener(sesion_id, sesion)
    from app.modules.evaluations.repository import RepositorioEvaluaciones

    convocatorias = servicio_sesiones.listar_convocatorias_para_participacion(modelo.id)
    convocatoria_ids = [convocatoria.id for convocatoria in convocatorias]
    participacion_ids = []
    from app.modules.participations.service import ServicioParticipaciones

    participaciones = ServicioParticipaciones(db)
    for convocatoria_id in convocatoria_ids:
        participacion_ids.extend(
            participacion.id
            for participacion in participaciones.listar_intentos_modelo(convocatoria_id)
        )
    filas = RepositorioEvaluaciones(db).retroalimentaciones_sesion(
        convocatoria_ids,
        participacion_ids,
    )
    return [
        RetroalimentacionDocenteSalida.model_validate(fila).model_dump(mode="json")
        for fila in filas
    ]
