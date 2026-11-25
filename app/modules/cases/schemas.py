from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.cases.schemas_composicion import (
    ComposicionDocenteSalida,
    ComposicionEstudianteSalida,
)
from app.modules.cases.schemas_puzzles import PuzzleDocenteSalida, PuzzleEstudianteSalida


class ErrorValidacionSalida(BaseModel):
    codigo: str
    mensaje: str
    ubicacion: str


class OpcionDocenteEntrada(BaseModel):
    texto: str = Field(min_length=1)
    es_correcta: bool = False
    justificacion: str = Field(min_length=1)


class OpcionDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    texto: str
    es_correcta: bool
    justificacion: str


class OpcionEstudianteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    texto: str


class PreguntaDocenteEntrada(BaseModel):
    enunciado: str = Field(min_length=1)


class PreguntaDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    enunciado: str
    opciones: list[OpcionDocenteSalida]


class PreguntaEstudianteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    enunciado: str
    opciones: list[OpcionEstudianteSalida]


class EscenarioDocenteEntrada(BaseModel):
    titulo: str = Field(min_length=1)
    contexto: str = Field(min_length=1)


class EscenarioDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    titulo: str
    contexto: str
    preguntas: list[PreguntaDocenteSalida]
    puzzles: list[PuzzleDocenteSalida] = Field(default_factory=list)
    composicion: ComposicionDocenteSalida | None = None


class EscenarioEstudianteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    titulo: str
    contexto: str
    preguntas: list[PreguntaEstudianteSalida]
    puzzles: list[PuzzleEstudianteSalida] = Field(default_factory=list)
    # None si el docente no armó una composición: el simulador usa solo el contexto de texto.
    composicion: ComposicionEstudianteSalida | None = None


class CriterioRubricaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str | None = None
    peso: Decimal
    pregunta_ids: list[str] = Field(default_factory=list)


class CriterioRubricaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    orden: int
    nombre: str
    descripcion: str | None
    peso: Decimal
    pregunta_ids: list[str] = Field(default_factory=list)


class RubricaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    descripcion: str | None = None
    escala_min: Decimal = Decimal("0.00")
    escala_max: Decimal = Decimal("5.00")
    nota_aprobatoria: Decimal = Decimal("3.00")
    publicada: bool = False
    criterios: list[CriterioRubricaEntrada] = Field(default_factory=list)


class RubricaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nombre: str
    descripcion: str | None
    escala_min: Decimal
    escala_max: Decimal
    nota_aprobatoria: Decimal
    publicada: bool
    criterios: list[CriterioRubricaSalida]


class CasoEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    desarrollo_situacional: str = Field(min_length=1)
    contexto_historia: str = Field(min_length=1)
    tiempo_estimado_min: int = Field(ge=1)


class CasoEditarEntrada(BaseModel):
    nombre: str | None = None
    desarrollo_situacional: str | None = None
    contexto_historia: str | None = None
    tiempo_estimado_min: int | None = Field(default=None, ge=1)


class CasoDocenteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    docente_creador_id: str
    nombre: str
    desarrollo_situacional: str
    contexto_historia: str
    tiempo_estimado_min: int
    estado: str
    version: int
    caso_origen_id: str | None
    publicado_en: datetime | None
    archivado_en: datetime | None
    creado_en: datetime
    actualizado_en: datetime
    escenarios: list[EscenarioDocenteSalida]
    rubrica: RubricaSalida | None


class CasoEstudianteSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nombre: str
    desarrollo_situacional: str
    contexto_historia: str
    tiempo_estimado_min: int
    estado: str
    version: int
    escenarios: list[EscenarioEstudianteSalida]


class ResultadoValidacion(BaseModel):
    valido: bool
    errores: list[ErrorValidacionSalida]


class EntradaOrden(BaseModel):
    ids: list[str] = Field(min_length=1)
