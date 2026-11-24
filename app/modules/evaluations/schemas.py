from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DetallePreguntaResultado(BaseModel):
    pregunta_id: str
    enunciado: str
    opcion_elegida_id: str | None
    opcion_correcta_id: str
    acertada: bool
    justificacion: str


class ResultadoParticipacionSalida(BaseModel):
    aciertos: int
    errores: int
    total_preguntas: int
    nota_final: Decimal
    nota_aprobatoria: Decimal
    es_parcial: bool
    es_ausencia: bool = False
    retroalimentacion: str | None = None
    preguntas: list[DetallePreguntaResultado]


class EntradaRetroalimentacionDocente(BaseModel):
    texto: str = Field(min_length=1)


class RetroalimentacionDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    participacion_id: str | None
    convocatoria_id: str | None
    docente_id: str
    texto: str
    creada_en: datetime
    actualizada_en: datetime
