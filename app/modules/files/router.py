from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.modules.files.dependencies import obtener_servicio_archivos
from app.modules.files.schemas import ArchivoSalida, EstadoGeneracionSalida, GenerarImagenEntrada
from app.modules.files.service import TAMANO_MAXIMO_BYTES, ServicioArchivos
from app.shared.dependencias_autenticacion import obtener_sesion, requerir_permiso

router = APIRouter(prefix="/archivos", tags=["M2 - Archivos del editor visual"])
permiso_crear_casos = requerir_permiso("CREAR_CASOS")


def _salida(servicio: ServicioArchivos, archivo) -> ArchivoSalida:
    return ArchivoSalida(
        id=archivo.id,
        nombre_original=archivo.nombre_original,
        tipo_mime=archivo.tipo_mime,
        tamano_bytes=archivo.tamano_bytes,
        url=servicio.url(archivo),
        origen=archivo.origen,
        prompt_generacion=archivo.prompt_generacion,
        creado_en=archivo.creado_en,
    )


@router.post("/escenarios", response_model=ArchivoSalida, status_code=201)
def subir_imagen(
    archivo: Annotated[UploadFile, File(description="JPG o PNG, máximo 5 MB")],
    sesion: Annotated[dict, Depends(permiso_crear_casos)],
    servicio: Annotated[ServicioArchivos, Depends(obtener_servicio_archivos)],
) -> ArchivoSalida:
    """Sube una imagen para el editor visual. El tipo se valida por el contenido real."""
    # Se lee un byte de más para detectar el exceso sin cargar archivos enormes en memoria.
    contenido = archivo.file.read(TAMANO_MAXIMO_BYTES + 1)
    return _salida(servicio, servicio.subir(sesion, archivo.filename, contenido))


@router.get("/generacion", response_model=EstadoGeneracionSalida)
def estado_generacion(
    sesion: Annotated[dict, Depends(permiso_crear_casos)],
    servicio: Annotated[ServicioArchivos, Depends(obtener_servicio_archivos)],
) -> EstadoGeneracionSalida:
    """¿Se pueden generar imágenes con IA ahora? Cuántas le quedan al docente esta hora."""
    return EstadoGeneracionSalida(**servicio.estado_generacion(sesion))


@router.post("/generar", response_model=ArchivoSalida, status_code=201)
def generar_imagen(
    solicitud: GenerarImagenEntrada,
    sesion: Annotated[dict, Depends(permiso_crear_casos)],
    servicio: Annotated[ServicioArchivos, Depends(obtener_servicio_archivos)],
) -> ArchivoSalida:
    """Genera una imagen con IA para un escenario (caso en borrador del propio docente)."""
    archivo = servicio.generar_imagen(
        sesion, solicitud.caso_id, solicitud.escenario_id, solicitud.prompt, solicitud.tamano
    )
    return _salida(servicio, archivo)


@router.get("", response_model=list[ArchivoSalida])
def listar_mis_archivos(
    sesion: Annotated[dict, Depends(permiso_crear_casos)],
    servicio: Annotated[ServicioArchivos, Depends(obtener_servicio_archivos)],
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[ArchivoSalida]:
    return [_salida(servicio, a) for a in servicio.listar(sesion, limite, desplazamiento)]


@router.delete("/{archivo_id}", status_code=204)
def eliminar_archivo(
    archivo_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion)],
    servicio: Annotated[ServicioArchivos, Depends(obtener_servicio_archivos)],
) -> None:
    servicio.eliminar(archivo_id, sesion)
