"""Composición visual de un escenario: modelos de capa y validación (editor visual, Fase 14).

Se guarda la COMPOSICIÓN (capas en JSON) y no una imagen plana, para poder editarla de nuevo.
Las coordenadas están en unidades del lienzo (`ancho` x `alto`); el navegador las escala.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Iconos SVG propios del proyecto: cada nombre es un archivo en frontend/static/iconos/.
ICONOS_PERMITIDOS = (
    "persona",
    "grupo",
    "corazon",
    "mensaje",
    "pregunta",
    "alerta",
    "escudo",
    "reloj",
    "casa",
    "libro",
    "estrella",
    "ojo",
)
MAX_CAPAS = 60
LIMITE_COORDENADA = 10000

ColorHex = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Alineacion = Literal["izquierda", "centro", "derecha"]
TipoForma = Literal["rectangulo", "rectangulo_redondeado", "circulo", "linea"]


class _CapaBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    # Posición en la pila (z-index): a mayor orden, más arriba. El servidor la renumera 1..n.
    orden: int = Field(default=1, ge=1, le=1000)
    x: float = Field(default=0, ge=-LIMITE_COORDENADA, le=LIMITE_COORDENADA)
    y: float = Field(default=0, ge=-LIMITE_COORDENADA, le=LIMITE_COORDENADA)
    ancho: float | None = Field(default=None, ge=0, le=LIMITE_COORDENADA)
    alto: float | None = Field(default=None, ge=0, le=LIMITE_COORDENADA)


class CapaImagen(_CapaBase):
    tipo: Literal["imagen"]
    archivo_id: str = Field(min_length=36, max_length=36)
    # La pone el servidor al guardar a partir de `archivo_id`; lo que envíe el cliente se ignora.
    url: str | None = None
    # "IA" queda reservado para la Fase 15; hoy toda imagen viene de un archivo subido.
    origen: Literal["SUBIDA", "IA"] = "SUBIDA"
    ajuste: Literal["cubrir", "contener", "estirar"] = "contener"
    opacidad: float = Field(default=1, ge=0, le=1)


class CapaTexto(_CapaBase):
    tipo: Literal["texto"]
    contenido: str = Field(min_length=1, max_length=1000)
    tamano: float = Field(default=48, ge=8, le=400)
    color: ColorHex = "#ffffff"
    alineacion: Alineacion = "izquierda"
    negrita: bool = False
    cursiva: bool = False


class CapaForma(_CapaBase):
    tipo: Literal["forma"]
    forma: TipoForma
    relleno: ColorHex | None = None
    borde_color: ColorHex | None = None
    borde_grosor: float = Field(default=0, ge=0, le=100)
    opacidad: float = Field(default=1, ge=0, le=1)
    radio: float = Field(default=24, ge=0, le=1000)


class CapaIcono(_CapaBase):
    tipo: Literal["icono"]
    icono: str
    color: ColorHex = "#ffffff"
    opacidad: float = Field(default=1, ge=0, le=1)

    @field_validator("icono")
    @classmethod
    def _icono_del_conjunto(cls, valor: str) -> str:
        if valor not in ICONOS_PERMITIDOS:
            raise ValueError(f"Icono no disponible: elige uno de {', '.join(ICONOS_PERMITIDOS)}")
        return valor


Capa = Annotated[CapaImagen | CapaTexto | CapaForma | CapaIcono, Field(discriminator="tipo")]
