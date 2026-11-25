from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.generacion_imagenes import LARGO_MAX_PROMPT

TamanoGeneracion = Literal["1024x1024", "1536x1024", "1024x1536"]


class ArchivoSalida(BaseModel):
    id: str
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    url: str
    origen: Literal["SUBIDO", "GENERADO_IA"]
    # Solo en las imágenes generadas: el docente lo ve para ajustarlo y regenerar.
    prompt_generacion: str | None = None
    creado_en: datetime


class GenerarImagenEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caso_id: str = Field(min_length=36, max_length=36)
    escenario_id: str = Field(min_length=36, max_length=36)
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LARGO_MAX_PROMPT)
    ]
    tamano: TamanoGeneracion = "1536x1024"


class TamanoSalida(BaseModel):
    valor: TamanoGeneracion
    ancho: int
    alto: int
    etiqueta: str


class EstadoGeneracionSalida(BaseModel):
    disponible: bool
    motivo: str | None
    max_por_hora: int
    restantes: int
    largo_max_prompt: int
    tamanos: list[TamanoSalida]
