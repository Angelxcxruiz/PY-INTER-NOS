from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencies import (
    obtener_servicio,
    obtener_usuario_actual,
)
from app.modules.auth.schemas import (
    PermisoRespuesta,
    RespuestaAcceso,
    RespuestaUsuario,
    SolicitudCrearUsuario,
    SolicitudEditarUsuario,
    SolicitudLogin,
    SolicitudLoginEstudiante,
)
from app.modules.auth.service import ServicioUsuarios
from app.shared.dependencias_autenticacion import requerir_rol

router = APIRouter(prefix="/auth", tags=["M1 - Autenticacion"])
router_administracion = APIRouter(
    prefix="/admin",
    tags=["M1 - Administracion"],
)


@router.post("/login", response_model=RespuestaAcceso)
def login(
    solicitud: SolicitudLogin,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaAcceso:
    token, usuario = servicio.login(solicitud.correo, solicitud.contrasena)
    return RespuestaAcceso(
        token_acceso=token,
        usuario=RespuestaUsuario.model_validate(usuario),
    )


@router.post("/student-login", response_model=RespuestaAcceso)
def login_estudiante(
    solicitud: SolicitudLoginEstudiante,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaAcceso:
    token, usuario = servicio.login_estudiante(solicitud.correo, solicitud.codigo)
    if usuario is None:
        return RespuestaAcceso(token_acceso=token)
    return RespuestaAcceso(
        token_acceso=token,
        usuario=RespuestaUsuario.model_validate(usuario),
    )


@router.get("/me", response_model=RespuestaUsuario)
def usuario_actual(
    usuario=Depends(obtener_usuario_actual),
) -> RespuestaUsuario:
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.get(
    "/users",
    response_model=list[RespuestaUsuario],
)
def listar_usuarios(
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[RespuestaUsuario]:
    del sesion
    usuarios = servicio.listar_usuarios(limite, desplazamiento)
    return [RespuestaUsuario.model_validate(usuario) for usuario in usuarios]


@router_administracion.post(
    "/users",
    response_model=RespuestaUsuario,
    status_code=201,
)
def crear_usuario(
    solicitud: SolicitudCrearUsuario,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.crear_usuario(
        solicitud.nombre,
        solicitud.correo,
        solicitud.contrasena,
        solicitud.rol,
        solicitud.activo,
    )
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.get(
    "/users/{usuario_id}",
    response_model=RespuestaUsuario,
)
def obtener_usuario(
    usuario_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    return RespuestaUsuario.model_validate(servicio.obtener_usuario(usuario_id))


@router_administracion.patch(
    "/users/{usuario_id}",
    response_model=RespuestaUsuario,
)
def editar_usuario(
    usuario_id: str,
    solicitud: SolicitudEditarUsuario,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.editar_usuario(
        usuario_id,
        solicitud.nombre,
        solicitud.contrasena,
        solicitud.rol,
        solicitud.activo,
    )
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.delete("/users/{usuario_id}", status_code=204)
def eliminar_usuario(
    usuario_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> None:
    del sesion
    servicio.eliminar_usuario(usuario_id)


@router_administracion.post(
    "/users/{usuario_id}/activate",
    response_model=RespuestaUsuario,
)
def activar_usuario(
    usuario_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    return RespuestaUsuario.model_validate(servicio.activar(usuario_id))


@router_administracion.post(
    "/users/{usuario_id}/deactivate",
    response_model=RespuestaUsuario,
)
def desactivar_usuario(
    usuario_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    return RespuestaUsuario.model_validate(servicio.desactivar(usuario_id))


@router_administracion.get(
    "/permissions",
    response_model=list[PermisoRespuesta],
)
def listar_permisos(
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> list[PermisoRespuesta]:
    del sesion
    return [PermisoRespuesta.model_validate(permiso) for permiso in servicio.listar_permisos()]


@router_administracion.put(
    "/users/{usuario_id}/permissions",
    response_model=RespuestaUsuario,
)
def sustituir_permisos(
    usuario_id: str,
    permisos_ids: list[str],
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.sustituir_permisos(usuario_id, permisos_ids)
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.post(
    "/users/{usuario_id}/permissions/{permiso_id}",
    response_model=RespuestaUsuario,
)
def asignar_permiso(
    usuario_id: str,
    permiso_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.asignar_permiso(usuario_id, permiso_id)
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.delete(
    "/users/{usuario_id}/permissions/{permiso_id}",
    response_model=RespuestaUsuario,
)
def quitar_permiso(
    usuario_id: str,
    permiso_id: str,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.quitar_permiso(usuario_id, permiso_id)
    return RespuestaUsuario.model_validate(usuario)
