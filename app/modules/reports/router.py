from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.modules.reports.csv_export import generar_csv
from app.modules.reports.dependencies import obtener_servicio_reportes
from app.modules.reports.service import ServicioReportes
from app.shared.dependencias_autenticacion import obtener_sesion

router = APIRouter(tags=["M7 - Seguimiento y reportes"])


@router.get(
    "/sessions/{sesion_id}/seguimiento",
)
def seguimiento(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> dict:
    return servicio.seguimiento(sesion_id, sesion)


@router.get("/sessions/{sesion_id}/estadisticas")
def estadisticas_sesion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> dict:
    return servicio.estadisticas_sesion(sesion_id, sesion)


@router.get("/cases/{caso_id}/estadisticas")
def estadisticas_caso(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> dict:
    return servicio.estadisticas_caso(caso_id, sesion)


@router.get("/espacios-academicos/{espacio_id}/estadisticas")
def estadisticas_espacio(
    espacio_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> dict:
    return servicio.estadisticas_espacio(espacio_id, sesion)


@router.get("/sessions/{sesion_id}/reports/participation.csv")
def csv_participacion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> StreamingResponse:
    filas = servicio.filas_csv_participacion(sesion_id, sesion)
    generator = generar_csv(
        [
            "nombre",
            "correo",
            "estado",
            "inicio",
            "fin",
            "preguntas respondidas",
            "total preguntas",
            "aciertos",
            "nota final",
            "parcial",
            "ausente",
            "retroalimentacion general",
        ],
        filas,
    )
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": (f'attachment; filename="participacion_{sesion_id}.csv"')},
    )


@router.get("/sessions/{sesion_id}/reports/answers.csv")
def csv_respuestas(
    sesion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioReportes, Depends(obtener_servicio_reportes)],
) -> StreamingResponse:
    filas = servicio.filas_csv_respuestas(sesion_id, sesion)
    generator = generar_csv(
        [
            "nombre",
            "correo",
            "escenario",
            "enunciado",
            "opcion elegida",
            "opcion correcta",
            "es correcta",
            "justificacion",
        ],
        filas,
    )
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": (f'attachment; filename="respuestas_{sesion_id}.csv"')},
    )
