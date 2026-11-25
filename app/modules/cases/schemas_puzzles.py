from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.cases.puzzles import TipoPuzzle, vista_estudiante


class PuzzleEntrada(BaseModel):
    """El contenido (con la solución) se valida por tipo en el servicio, no aquí."""

    tipo: TipoPuzzle
    enunciado: str = Field(min_length=1, max_length=300)
    contenido: dict[str, Any]


class PuzzleDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    tipo: str
    enunciado: str
    contenido: dict[str, Any]
    creado_en: datetime


class PuzzleEstudianteSalida(BaseModel):
    """Lo que ve quien va a jugar: elementos barajados y SIN solución."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    tipo: str
    enunciado: str
    tiempo_seg: int
    datos: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _desde_puzzle(cls, valor: Any) -> Any:
        if isinstance(valor, dict):
            return valor
        tiempo, datos = vista_estudiante(valor.tipo, valor.contenido)
        return {
            "id": valor.id,
            "orden": valor.orden,
            "tipo": valor.tipo,
            "enunciado": valor.enunciado,
            "tiempo_seg": tiempo,
            "datos": datos,
        }


class VerificarPuzzleEntrada(BaseModel):
    respuesta: dict[str, Any]


class VerificarPuzzleSalida(BaseModel):
    """Solo dice si acertó: nunca devuelve la solución."""

    acerto: bool
