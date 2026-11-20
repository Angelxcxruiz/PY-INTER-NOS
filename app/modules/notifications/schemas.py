from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificacionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    usuario_id: str
    tipo: str
    titulo: str
    mensaje: str
    leida_en: datetime | None
    evento_id: str
    creada_en: datetime


class EntregaCorreoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    evento_id: str
    destinatario: str
    tipo: str
    estado: str
    intentos: int
    ultimo_error: str | None
    enviado_en: datetime | None
    creada_en: datetime
