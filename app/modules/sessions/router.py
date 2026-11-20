from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.sessions.dependencies import obtener_servicio_sesiones
from app.modules.sessions.schemas import (
    ConvocadoEntrada,
    ConvocatoriaCodigoSalida,
    ConvocatoriaSalida,
    DatosEspacioAcademico,
    EspacioAcademicoSalida,
    SesionEditarEntrada,
    SesionEntrada,
    SesionSalida,
)
from app.modules.sessions.service import ServicioSesiones
from app.shared.dependencias_autenticacion import requerir_rol

router = APIRouter(tags=["M3 - Sesiones y convocatorias"])
solo_docente_admin = requerir_rol("ADMINISTRADOR", "DOCENTE")


@router.post(
    "/espacios-academicos",
    response_model=EspacioAcademicoSalida,
    status_code=201,
)
def crear_espacio(
    datos: DatosEspacioAcademico,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> EspacioAcademicoSalida:
    espacio = servicio.crear_espacio(sesion, datos.nombre, datos.codigo)
    return EspacioAcademicoSalida.model_validate(espacio)


@router.get("/espacios-academicos", response_model=list[EspacioAcademicoSalida])
def listar_espacios(
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> list[EspacioAcademicoSalida]:
    return [
        EspacioAcademicoSalida.model_validate(espacio)
        for espacio in servicio.listar_espacios(sesion)
    ]


@router.post("/sessions", response_model=SesionSalida, status_code=201)
def crear_sesion(
    solicitud: SesionEntrada,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> SesionSalida:
    return SesionSalida.model_validate(servicio.crear(sesion, solicitud))


@router.get("/sessions", response_model=list[SesionSalida])
def listar_sesiones(
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
    estado: Annotated[str | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[SesionSalida]:
    return [
        SesionSalida.model_validate(modelo)
        for modelo in servicio.listar(sesion, estado, limite, desplazamiento)
    ]


@router.get("/sessions/{sesion_id}", response_model=SesionSalida)
def consultar_sesion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> SesionSalida:
    return SesionSalida.model_validate(servicio.obtener(sesion_id, sesion))


@router.put("/sessions/{sesion_id}", response_model=SesionSalida)
def reprogramar_sesion(
    sesion_id: str,
    solicitud: SesionEditarEntrada,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> SesionSalida:
    return SesionSalida.model_validate(
        servicio.reprogramar(sesion_id, solicitud, sesion),
    )


@router.post("/sessions/{sesion_id}/start", response_model=SesionSalida)
def iniciar_sesion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> SesionSalida:
    return SesionSalida.model_validate(servicio.iniciar(sesion_id, sesion))


@router.post("/sessions/{sesion_id}/finish", response_model=SesionSalida)
def finalizar_sesion(
    sesion_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> SesionSalida:
    return SesionSalida.model_validate(servicio.finalizar(sesion_id, sesion))


@router.get(
    "/sessions/{sesion_id}/convocatorias",
    response_model=list[ConvocatoriaSalida],
)
def listar_convocatorias(
    sesion_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> list[ConvocatoriaSalida]:
    return [
        ConvocatoriaSalida.model_validate(convocatoria)
        for convocatoria in servicio.listar_convocatorias(sesion_id, sesion)
    ]


@router.post(
    "/sessions/{sesion_id}/convocatorias",
    response_model=list[ConvocatoriaSalida],
)
def agregar_convocatorias(
    sesion_id: str,
    convocados: list[ConvocadoEntrada],
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> list[ConvocatoriaSalida]:
    creadas = servicio.agregar_convocados(sesion_id, convocados, sesion)
    return [ConvocatoriaSalida.model_validate(convocatoria) for convocatoria in creadas]


@router.delete(
    "/sessions/{sesion_id}/convocatorias/{convocatoria_id}",
    status_code=204,
)
def retirar_convocatoria(
    sesion_id: str,
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> None:
    servicio.retirar_convocado(sesion_id, convocatoria_id, sesion)


@router.get(
    "/sessions/{sesion_id}/convocatorias/{convocatoria_id}/codigo",
    response_model=ConvocatoriaCodigoSalida,
)
def ver_codigo(
    sesion_id: str,
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> ConvocatoriaCodigoSalida:
    codigo = servicio.ver_codigo(sesion_id, convocatoria_id, sesion)
    return ConvocatoriaCodigoSalida(id=convocatoria_id, codigo=codigo)


@router.post(
    "/sessions/{sesion_id}/convocatorias/{convocatoria_id}/codigo/regenerar",
    response_model=ConvocatoriaCodigoSalida,
)
def regenerar_codigo(
    sesion_id: str,
    convocatoria_id: str,
    sesion: Annotated[dict, Depends(solo_docente_admin)],
    servicio: Annotated[ServicioSesiones, Depends(obtener_servicio_sesiones)],
) -> ConvocatoriaCodigoSalida:
    codigo = servicio.regenerar_codigo(sesion_id, convocatoria_id, sesion)
    return ConvocatoriaCodigoSalida(id=convocatoria_id, codigo=codigo)
