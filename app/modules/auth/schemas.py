from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RespuestaUsuario(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    correo: str
    rol: str
    activo: bool
    correo_verificado: bool = False
    estado_cuenta: str = "ACTIVO"
    aprobado_en: datetime | None = None
    creado_en: datetime
    actualizado_en: datetime


class SolicitudRegistro(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    correo: EmailStr
    contrasena: str = Field(min_length=8, max_length=128)
    # El administrador no se acepta aquí: se crea por seed o por otro administrador.
    rol: Literal["ESTUDIANTE", "DOCENTE"]


class RespuestaRegistro(BaseModel):
    """Nunca incluye el código. Las dos cifras permiten al frontend dibujar los contadores."""

    usuario_id: str
    correo: str
    mensaje: str
    vigencia_segundos: int
    reenvio_segundos: int


class SolicitudVerificarRegistro(BaseModel):
    correo: EmailStr
    codigo: str = Field(min_length=1, max_length=20)


class RespuestaVerificacionRegistro(BaseModel):
    mensaje: str
    rol: str
    estado_cuenta: str


class SolicitudReenviarCodigo(BaseModel):
    correo: EmailStr


class RespuestaReenvioCodigo(BaseModel):
    mensaje: str
    vigencia_segundos: int
    reenvio_segundos: int


class SolicitudDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    correo: str
    estado_cuenta: str
    creado_en: datetime


class SolicitudAprobacion(BaseModel):
    permisos: list[str] = Field(default_factory=list, max_length=20)


class SolicitudRechazo(BaseModel):
    motivo: str | None = Field(default=None, max_length=1000)


class SolicitudOlvideContrasena(BaseModel):
    correo: EmailStr


class SolicitudRestablecerContrasena(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    nueva_contrasena: str = Field(min_length=8, max_length=128)


class SolicitudConfirmarCorreo(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class SolicitudReenviarVerificacion(BaseModel):
    correo: EmailStr


class RespuestaMensaje(BaseModel):
    mensaje: str


class SolicitudLogin(BaseModel):
    correo: EmailStr
    contrasena: str = Field(min_length=1)


class SolicitudLoginEstudiante(BaseModel):
    correo: EmailStr
    codigo: str = Field(min_length=1)


class RespuestaAcceso(BaseModel):
    token_acceso: str
    tipo_token: str = "Bearer"
    usuario: RespuestaUsuario | None = None


class SolicitudCrearUsuario(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    correo: EmailStr
    contrasena: str | None = Field(default=None, min_length=8)
    rol: str
    activo: bool = True


class SolicitudEditarUsuario(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    contrasena: str | None = Field(default=None, min_length=8)
    rol: str | None = None
    activo: bool | None = None


class PermisoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    codigo: str
    nombre: str
    descripcion: str | None = None
