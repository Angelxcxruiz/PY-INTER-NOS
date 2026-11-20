from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RespuestaUsuario(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    correo: str
    rol: str
    activo: bool
    creado_en: datetime
    actualizado_en: datetime


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
