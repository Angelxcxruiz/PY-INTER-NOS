from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ConvocadoReporte(BaseModel):
    nombre: str
    correo: str
    estado: str
    iniciada_en: datetime | None = None
    finalizada_en: datetime | None = None
    respondidas: int
    total_preguntas: int
    aciertos: int | None = None
    nota_final: Decimal | None = None
    parcial: bool = False
    ausente: bool = False
    retroalimentacion: str = ""


class EstadisticasReporte(BaseModel):
    total_convocados: int
    tasa_participacion: Decimal | None
    tasa_finalizacion: Decimal | None
    tasa_expiracion: Decimal | None
    tasa_ausencia: Decimal | None
    promedio: Decimal | None
    mediana: Decimal | None
    nota_minima: Decimal | None
    nota_maxima: Decimal | None


class SeguimientoReporte(BaseModel):
    convocados: list[ConvocadoReporte]
    estadisticas: EstadisticasReporte
