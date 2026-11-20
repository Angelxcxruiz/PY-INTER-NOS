from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class EntradaRespuesta(BaseModel):
    opcion_id: str


class RespuestaActualSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pregunta_id: str
    opcion_id: str
    respondida_en: datetime
    actualizada_en: datetime


class ProgresoSalida(BaseModel):
    respondidas: int
    total: int
    porcentaje: Decimal
    segundos_restantes: int


class ParticipacionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    convocatoria_id: str
    numero_intento: int
    iniciada_en: datetime
    vence_en: datetime
    finalizada_en: datetime | None
    estado: str
    motivo_cierre: str | None
    progreso: ProgresoSalida
    respuestas_actuales: list[RespuestaActualSalida]


class ResultadoRespuestaSalida(BaseModel):
    respondidas: int
    total: int
    porcentaje: Decimal
    segundos_restantes: int


class EntradaAutorizacionRepeticion(BaseModel):
    motivo: str | None = None


class IntentoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    numero_intento: int
    iniciada_en: datetime
    finalizada_en: datetime | None
    estado: str
    motivo_cierre: str | None
