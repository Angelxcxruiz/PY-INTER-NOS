import logging
import re
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.almacenamiento import PuertoAlmacenamiento, obtener_almacenamiento
from app.core.clock import Reloj, ahora
from app.core.exceptions import (
    ErrorArchivoDemasiadoGrande,
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorTipoArchivo,
    ErrorValidacion,
)
from app.modules.files.models import ArchivoAdjunto
from app.modules.files.repository import RepositorioArchivos

registro = logging.getLogger(__name__)

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024
CARPETA_ESCENARIOS = "escenarios"

# Se reconoce el tipo por los primeros bytes del contenido (firma), no por la extensión ni por
# el Content-Type que declara el navegador, que el usuario puede falsear.
_FIRMAS = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)


def detectar_tipo(contenido: bytes) -> tuple[str, str]:
    """Devuelve (tipo_mime, extensión) según la firma real del archivo."""
    for firma, tipo_mime, extension in _FIRMAS:
        if contenido.startswith(firma):
            return tipo_mime, extension
    raise ErrorTipoArchivo(
        "Solo se admiten imágenes JPG o PNG. Revisa que el archivo no esté dañado "
        "ni sea de otro formato con la extensión cambiada.",
        detalles={"permitidos": ["image/jpeg", "image/png"]},
    )


def _nombre_limpio(nombre: str | None) -> str:
    base = re.split(r"[\\/]", nombre or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base or "imagen")[:255]


class ServicioArchivos:
    def __init__(
        self,
        db: Session,
        almacenamiento: PuertoAlmacenamiento | None = None,
        reloj: Reloj | None = None,
        esta_en_uso: Callable[[str], bool] | None = None,
    ) -> None:
        self.db = db
        self.repositorio = RepositorioArchivos(db)
        self.almacenamiento = almacenamiento or obtener_almacenamiento()
        self.reloj = reloj
        # Quién usa el archivo lo sabe el módulo de casos; se inyecta para no acoplar módulos.
        self.esta_en_uso = esta_en_uso

    def url(self, archivo: ArchivoAdjunto) -> str:
        return self.almacenamiento.url_publica(archivo.ruta_almacenamiento)

    def subir(self, sesion: dict, nombre_original: str | None, contenido: bytes) -> ArchivoAdjunto:
        """Registra un archivo del docente. Punto de entrada también para la Fase 15 (IA)."""
        if not contenido:
            raise ErrorValidacion("El archivo está vacío")
        if len(contenido) > TAMANO_MAXIMO_BYTES:
            raise ErrorArchivoDemasiadoGrande(
                "La imagen supera el máximo de 5 MB. Reduce su tamaño e inténtalo de nuevo.",
                detalles={"maximo_bytes": TAMANO_MAXIMO_BYTES},
            )
        tipo_mime, extension = detectar_tipo(contenido)
        nombre_guardado = f"{CARPETA_ESCENARIOS}/{uuid.uuid4()}.{extension}"
        ruta = self.almacenamiento.guardar(contenido, nombre_guardado, tipo_mime)
        try:
            archivo = self.repositorio.agregar(
                ArchivoAdjunto(
                    docente_id=sesion["sub"],
                    nombre_original=_nombre_limpio(nombre_original),
                    tipo_mime=tipo_mime,
                    tamano_bytes=len(contenido),
                    ruta_almacenamiento=ruta,
                    creado_en=ahora(self.reloj),
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._borrar_fisico(ruta)
            raise
        return archivo

    def listar(self, sesion: dict, limite: int, desplazamiento: int) -> list[ArchivoAdjunto]:
        return self.repositorio.listar_de_docente(sesion["sub"], limite, desplazamiento)

    def eliminar(self, archivo_id: str, sesion: dict) -> None:
        archivo = self.repositorio.por_id(archivo_id)
        if archivo is None:
            raise ErrorNoEncontrado("Archivo no encontrado")
        if sesion.get("rol") != "ADMINISTRADOR" and archivo.docente_id != sesion["sub"]:
            raise ErrorPermiso("Solo quien subió el archivo puede borrarlo")
        if self.esta_en_uso is not None and self.esta_en_uso(archivo.id):
            raise ErrorConflicto(
                "La imagen se usa en la composición de un escenario. Quítala de allí primero.",
            )
        ruta = archivo.ruta_almacenamiento
        self.repositorio.eliminar(archivo)
        self.db.commit()
        self._borrar_fisico(ruta)

    def resolver_urls(self, archivo_ids: list[str], propietarios: set[str]) -> dict[str, str]:
        """URL pública de cada archivo; falla si no existe o no es de alguno de `propietarios`."""
        pedidos = set(archivo_ids)
        encontrados = {archivo.id: archivo for archivo in self.repositorio.por_ids(list(pedidos))}
        urls: dict[str, str] = {}
        for archivo_id in pedidos:
            archivo = encontrados.get(archivo_id)
            if archivo is None or archivo.docente_id not in propietarios:
                raise ErrorValidacion(
                    "Una de las imágenes de la composición no existe o no es tuya",
                    detalles={"archivo_id": archivo_id},
                )
            urls[archivo_id] = self.url(archivo)
        return urls

    def _borrar_fisico(self, ruta: str) -> None:
        try:
            self.almacenamiento.eliminar(ruta)
        except Exception:  # un archivo huérfano en disco no debe tumbar la petición
            registro.exception("No se pudo borrar el archivo almacenado %s", ruta)
