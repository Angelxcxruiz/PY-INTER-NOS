"""Almacenamiento de archivos detrás de un puerto.

Ningún módulo escribe en disco directamente: pide un `PuertoAlmacenamiento`. Hoy la única
implementación operativa es `AlmacenamientoLocal`; `AlmacenamientoS3` queda documentada para
cuando el despliegue en AWS lo requiera.
"""

import os
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core.config import obtener_configuracion

PREFIJO_MEDIA = "/media"


class PuertoAlmacenamiento(Protocol):
    def guardar(self, contenido: bytes, nombre: str, tipo_mime: str) -> str:
        """Guarda el contenido bajo `nombre` (ruta relativa) y devuelve la ruta almacenada."""
        ...

    def url_publica(self, ruta: str) -> str:
        """URL con la que el navegador lee el archivo guardado en `ruta`."""
        ...

    def eliminar(self, ruta: str) -> None:
        """Borra el archivo. Si ya no existe, no es un error."""
        ...


class AlmacenamientoLocal:
    """Guarda en una carpeta del disco (por defecto `uploads/`), servida en `/media`."""

    def __init__(self, directorio: str | Path) -> None:
        self.directorio = Path(directorio).resolve()

    def _resolver(self, ruta: str) -> Path:
        relativa = PurePosixPath(ruta)
        if relativa.is_absolute() or ".." in relativa.parts or not relativa.parts:
            raise ValueError("Ruta de almacenamiento no permitida")
        destino = (self.directorio / relativa).resolve()
        if self.directorio not in destino.parents:
            raise ValueError("Ruta de almacenamiento fuera del directorio de archivos")
        return destino

    def guardar(self, contenido: bytes, nombre: str, tipo_mime: str) -> str:
        del tipo_mime  # el disco no necesita el tipo; S3 sí lo guardaría como metadato
        destino = self._resolver(nombre)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe en un temporal y se renombra: un fallo a medias no deja un archivo parcial.
        temporal = destino.with_name(destino.name + ".parcial")
        try:
            temporal.write_bytes(contenido)
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
        return PurePosixPath(nombre).as_posix()

    def url_publica(self, ruta: str) -> str:
        return f"{PREFIJO_MEDIA}/{PurePosixPath(ruta).as_posix()}"

    def eliminar(self, ruta: str) -> None:
        self._resolver(ruta).unlink(missing_ok=True)


class AlmacenamientoS3:
    """Reservado para AWS. Sin implementar a propósito: ningún código lo usa todavía.

    Cuando se migre, `guardar` hará `put_object(Bucket, Key=nombre, Body=contenido,
    ContentType=tipo_mime)`, `url_publica` devolverá la URL del bucket o de CloudFront, y
    `eliminar` hará `delete_object`. Las rutas ya guardadas en `archivo_adjunto` se conservan.
    """

    def guardar(self, contenido: bytes, nombre: str, tipo_mime: str) -> str:
        raise NotImplementedError("El almacenamiento en S3 aún no está implementado")

    def url_publica(self, ruta: str) -> str:
        raise NotImplementedError("El almacenamiento en S3 aún no está implementado")

    def eliminar(self, ruta: str) -> None:
        raise NotImplementedError("El almacenamiento en S3 aún no está implementado")


def directorio_media() -> Path:
    """Carpeta raíz que se publica en `/media` (se crea si no existe)."""
    directorio = Path(obtener_configuracion().almacenamiento_dir).resolve()
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio


def obtener_almacenamiento() -> PuertoAlmacenamiento:
    configuracion = obtener_configuracion()
    if configuracion.almacenamiento_backend.lower() == "s3":
        return AlmacenamientoS3()
    return AlmacenamientoLocal(configuracion.almacenamiento_dir)
