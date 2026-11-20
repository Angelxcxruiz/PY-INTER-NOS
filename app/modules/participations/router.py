from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.participations.dependencies import obtener_servicio_participaciones
from app.modules.participations.schemas import (
    EntradaAutorizacionRepeticion,
    EntradaRespuesta,
    ParticipacionSalida,
    ResultadoRespuestaSalida,
)
from app.modules.participations.service import ServicioParticipaciones
from app.shared.dependencias_autenticacion import requerir_rol

router = APIRouter(tags=["M4 - Participaciones"])
estudiante = requerir_rol("ESTUDIANTE")
docente = requerir_rol("DOCENTE", "ADMINISTRADOR")


@router.post("/participations/start/{convocatoria_id}", response_model=ParticipacionSalida)
def iniciar_participacion(
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(estudiante)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> ParticipacionSalida:
    participacion = servicio.iniciar(convocatoria_id, sesion)
    detalle = servicio.obtener_detalle(participacion.id, sesion)
    return ParticipacionSalida.model_validate(detalle)


@router.get(
    "/participations/by-convocatoria/{convocatoria_id}",
    response_model=ParticipacionSalida,
)
def participacion_vigente(
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(estudiante)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> ParticipacionSalida:
    participacion = servicio.por_convocatoria(convocatoria_id, sesion)
    detalle = servicio.obtener_detalle(participacion.id, sesion)
    return ParticipacionSalida.model_validate(detalle)


@router.get(
    "/participations/{participacion_id}",
    response_model=ParticipacionSalida,
)
def obtener_participacion(
    participacion_id: str,
    sesion: Annotated[dict, Depends(estudiante)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> ParticipacionSalida:
    detalle = servicio.obtener_detalle(participacion_id, sesion)
    return ParticipacionSalida.model_validate(detalle)


@router.put(
    "/participations/{participacion_id}/answers/{pregunta_id}",
    response_model=ResultadoRespuestaSalida,
)
def responder(
    participacion_id: str,
    pregunta_id: str,
    entrada: EntradaRespuesta,
    sesion: Annotated[dict, Depends(estudiante)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> ResultadoRespuestaSalida:
    resultado = servicio.responder(
        participacion_id,
        pregunta_id,
        entrada.opcion_id,
        sesion,
    )
    return ResultadoRespuestaSalida.model_validate(resultado)


@router.post(
    "/participations/{participacion_id}/finish",
)
def finalizar_participacion(
    participacion_id: str,
    sesion: Annotated[dict, Depends(estudiante)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> dict:
    return servicio.finalizar(participacion_id, sesion)


@router.post(
    "/participations/convocatorias/{convocatoria_id}/autorizar-repeticion",
)
def autorizar_repeticion(
    convocatoria_id: str,
    entrada: EntradaAutorizacionRepeticion,
    sesion: Annotated[dict, Depends(docente)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> dict:
    autorizacion = servicio.autorizar_repeticion(
        convocatoria_id,
        entrada.motivo,
        sesion,
    )
    return {
        "id": autorizacion.id,
        "convocatoria_id": autorizacion.convocatoria_id,
        "creada_en": autorizacion.creada_en,
        "usada_en": autorizacion.usada_en,
    }


@router.get(
    "/participations/convocatorias/{convocatoria_id}/intentos",
)
def listar_intentos(
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(docente)],
    servicio: Annotated[ServicioParticipaciones, Depends(obtener_servicio_participaciones)],
) -> list[dict]:
    intentos = servicio.listar_intentos(convocatoria_id, sesion)
    return [
        {
            "id": intento.id,
            "numero_intento": intento.numero_intento,
            "iniciada_en": intento.iniciada_en,
            "finalizada_en": intento.finalizada_en,
            "estado": intento.estado,
            "motivo_cierre": intento.motivo_cierre,
        }
        for intento in intentos
    ]
