from enum import StrEnum


class EstadoCaso(StrEnum):
    BORRADOR = "BORRADOR"
    PUBLICADO = "PUBLICADO"
    ARCHIVADO = "ARCHIVADO"


class EstadoSesion(StrEnum):
    SIN_INICIAR = "SIN_INICIAR"
    EN_CURSO = "EN_CURSO"
    FINALIZADO = "FINALIZADO"


class FinalizadaPor(StrEnum):
    DOCENTE = "DOCENTE"
    SISTEMA = "SISTEMA"
