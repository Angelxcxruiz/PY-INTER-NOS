from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app.modules.auth.dependencies import (
    obtener_despacho,
    obtener_servicio,
    obtener_usuario_actual,
)
from app.modules.auth.schemas import (
    PermisoRespuesta,
    RespuestaAcceso,
    RespuestaMensaje,
    RespuestaReenvioCodigo,
    RespuestaRegistro,
    RespuestaUsuario,
    RespuestaVerificacionRegistro,
    SolicitudAprobacion,
    SolicitudConfirmarCorreo,
    SolicitudCrearUsuario,
    SolicitudDocenteSalida,
    SolicitudEditarUsuario,
    SolicitudLogin,
    SolicitudLoginEstudiante,
    SolicitudOlvideContrasena,
    SolicitudRechazo,
    SolicitudReenviarCodigo,
    SolicitudReenviarVerificacion,
    SolicitudRegistro,
    SolicitudRestablecerContrasena,
    SolicitudVerificarRegistro,
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


MENSAJE_SOLICITUD = "Si el correo esta registrado, recibiras las instrucciones en breve."


@router.post("/forgot-password", response_model=RespuestaMensaje, status_code=202)
def olvide_contrasena(
    solicitud: SolicitudOlvideContrasena,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaMensaje:
    servicio.solicitar_restablecimiento(solicitud.correo)
    return RespuestaMensaje(mensaje=MENSAJE_SOLICITUD)


@router.post("/reset-password", response_model=RespuestaMensaje)
def restablecer_contrasena(
    solicitud: SolicitudRestablecerContrasena,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaMensaje:
    servicio.restablecer_contrasena(solicitud.token, solicitud.nueva_contrasena)
    return RespuestaMensaje(mensaje="Contrasena actualizada. Ya puede iniciar sesion.")


@router.post("/verificar-correo", response_model=RespuestaMensaje)
def verificar_correo(
    solicitud: SolicitudConfirmarCorreo,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaMensaje:
    servicio.confirmar_verificacion(solicitud.token)
    return RespuestaMensaje(mensaje="Correo verificado.")


@router.post("/reenviar-verificacion", response_model=RespuestaMensaje)
def reenviar_verificacion(
    solicitud: SolicitudReenviarVerificacion,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
) -> RespuestaMensaje:
    servicio.reenviar_verificacion(solicitud.correo)
    return RespuestaMensaje(mensaje="Si el correo existe, se envio un enlace de verificacion.")


@router.post("/registro", response_model=RespuestaRegistro, status_code=201)
def registro(
    solicitud: SolicitudRegistro,
    segundo_plano: BackgroundTasks,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
    despachar: Annotated[Callable[[], int], Depends(obtener_despacho)],
) -> RespuestaRegistro:
    """Crea la cuenta SIN_VERIFICAR y envía un código de 6 dígitos. Jamás lo devuelve."""
    usuario = servicio.registrar(
        solicitud.nombre, solicitud.correo, solicitud.contrasena, solicitud.rol
    )
    segundo_plano.add_task(despachar)
    configuracion = servicio.configuracion
    return RespuestaRegistro(
        usuario_id=usuario.id,
        correo=usuario.correo,
        mensaje=(
            "Te enviamos un código de 6 dígitos a tu correo. Ingrésalo para completar tu registro."
        ),
        vigencia_segundos=configuracion.codigo_registro_expira_min * 60,
        reenvio_segundos=configuracion.codigo_registro_cooldown_seg,
    )


@router.post("/registro/verificar", response_model=RespuestaVerificacionRegistro)
def verificar_registro(
    solicitud: SolicitudVerificarRegistro,
    segundo_plano: BackgroundTasks,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
    despachar: Annotated[Callable[[], int], Depends(obtener_despacho)],
) -> RespuestaVerificacionRegistro:
    usuario = servicio.verificar_registro(solicitud.correo, solicitud.codigo)
    segundo_plano.add_task(despachar)
    if usuario.rol == "ESTUDIANTE":
        mensaje = "Correo verificado: ya puedes ingresar."
    else:
        mensaje = "Correo verificado: tu cuenta será revisada por el administrador."
    return RespuestaVerificacionRegistro(
        mensaje=mensaje, rol=usuario.rol, estado_cuenta=usuario.estado_cuenta
    )


@router.post("/registro/reenviar", response_model=RespuestaReenvioCodigo)
def reenviar_codigo_registro(
    solicitud: SolicitudReenviarCodigo,
    segundo_plano: BackgroundTasks,
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)],
    despachar: Annotated[Callable[[], int], Depends(obtener_despacho)],
) -> RespuestaReenvioCodigo:
    """Responde SIEMPRE lo mismo, exista o no el correo, para no filtrar quién está registrado."""
    if servicio.reenviar_codigo_registro(solicitud.correo):
        segundo_plano.add_task(despachar)
    configuracion = servicio.configuracion
    return RespuestaReenvioCodigo(
        mensaje="Si el correo existe y está sin verificar, se envió un código nuevo.",
        vigencia_segundos=configuracion.codigo_registro_expira_min * 60,
        reenvio_segundos=configuracion.codigo_registro_cooldown_seg,
    )


@router_administracion.get(
    "/users",
    response_model=list[RespuestaUsuario],
)
@router_administracion.get(
    "/usuarios",
    response_model=list[RespuestaUsuario],
    include_in_schema=False,
)
def listar_usuarios(
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
    estado_cuenta: Annotated[str | None, Query()] = None,
) -> list[RespuestaUsuario]:
    del sesion
    usuarios = servicio.listar_usuarios(limite, desplazamiento, estado_cuenta)
    return [RespuestaUsuario.model_validate(usuario) for usuario in usuarios]


@router_administracion.get(
    "/solicitudes",
    response_model=list[SolicitudDocenteSalida],
)
def listar_solicitudes(
    respuesta: Response,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[SolicitudDocenteSalida]:
    del sesion
    respuesta.headers["X-Total-Count"] = str(servicio.contar_solicitudes())
    solicitudes = servicio.listar_solicitudes(limite, desplazamiento)
    return [SolicitudDocenteSalida.model_validate(usuario) for usuario in solicitudes]


@router_administracion.post(
    "/solicitudes/{usuario_id}/aprobar",
    response_model=RespuestaUsuario,
)
def aprobar_solicitud(
    usuario_id: str,
    entrada: SolicitudAprobacion | None = None,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    permisos = entrada.permisos if entrada is not None else []
    usuario = servicio.aprobar_solicitud(usuario_id, permisos, str(sesion["sub"]))
    return RespuestaUsuario.model_validate(usuario)


@router_administracion.post(
    "/solicitudes/{usuario_id}/rechazar",
    response_model=RespuestaUsuario,
)
def rechazar_solicitud(
    usuario_id: str,
    entrada: SolicitudRechazo | None = None,
    sesion=Depends(requerir_rol("ADMINISTRADOR")),
    servicio: Annotated[ServicioUsuarios, Depends(obtener_servicio)] = None,
) -> RespuestaUsuario:
    del sesion
    usuario = servicio.rechazar_solicitud(usuario_id, entrada.motivo if entrada else None)
    return RespuestaUsuario.model_validate(usuario)


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
