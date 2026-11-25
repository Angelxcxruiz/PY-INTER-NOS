from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.cases.composicion import MAX_CAPAS, Capa, ColorHex


class ComposicionEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ancho: int = Field(default=1280, ge=320, le=3840)
    alto: int = Field(default=720, ge=180, le=2160)
    fondo_color: ColorHex = "#0b0c2b"
    capas: list[Capa] = Field(default_factory=list, max_length=MAX_CAPAS)

    @model_validator(mode="after")
    def _ids_unicos_y_orden_continuo(self) -> "ComposicionEntrada":
        ids = [capa.id for capa in self.capas]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada capa debe tener un id distinto")
        # sorted es estable: a igual orden se conserva la posición recibida.
        self.capas = sorted(self.capas, key=lambda capa: capa.orden)
        for posicion, capa in enumerate(self.capas, start=1):
            capa.orden = posicion
        return self


class ComposicionEstudianteSalida(BaseModel):
    """Lo que ve el estudiante: el lienzo ya armado, sin metadatos de edición."""

    model_config = ConfigDict(from_attributes=True)
    ancho: int
    alto: int
    fondo_color: str
    capas: list[Capa]


class ComposicionDocenteSalida(ComposicionEstudianteSalida):
    id: str
    escenario_id: str
    creado_en: datetime
    actualizado_en: datetime
