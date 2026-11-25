from datetime import datetime

from pydantic import BaseModel


class ArchivoSalida(BaseModel):
    id: str
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    url: str
    creado_en: datetime
