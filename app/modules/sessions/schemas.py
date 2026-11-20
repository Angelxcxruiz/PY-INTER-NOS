from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatosEspacioAcademico(BaseModel):
    nombre: str = Field(min_length=1)
    codigo: str | None = None


class EspacioAcademicoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nombre: str
    codigo: str | None
    docente_id: str
    creado_en: datetime


class ConvocadoEntrada(BaseModel):
    correo: str = Field(min_length=3)
    nombre: str = Field(min_length=1)


class SesionEntrada(BaseModel):
    caso_id: str
    inicio_programado: datetime
    fin_programado: datetime
    tiempo_maximo_min: int = Field(gt=0)
    lugar_fisico: str | None = None
    mensaje_personalizado: str | None = None
    espacio_academico_id: str | None = None
    espacio_academico: DatosEspacioAcademico | None = None
    convocados: list[ConvocadoEntrada] = Field(default_factory=list)


class SesionEditarEntrada(BaseModel):
    inicio_programado: datetime | None = None
    fin_programado: datetime | None = None
    tiempo_maximo_min: int | None = Field(default=None, gt=0)
    lugar_fisico: str | None = None
    mensaje_personalizado: str | None = None


class ConvocatoriaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sesion_id: str
    estudiante_id: str
    codigo_vigente: bool
    revocada_en: datetime | None
    creada_en: datetime


class ConvocatoriaCodigoSalida(BaseModel):
    id: str
    codigo: str


class SesionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    caso_id: str
    docente_id: str
    espacio_academico_id: str
    inicio_programado: datetime
    fin_programado: datetime
    tiempo_maximo_min: int
    lugar_fisico: str | None
    mensaje_personalizado: str | None
    estado: str
    iniciada_en: datetime | None
    finalizada_en: datetime | None
    finalizada_por: str | None
    creada_en: datetime
