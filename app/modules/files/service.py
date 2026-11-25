import logging
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.almacenamiento import PuertoAlmacenamiento, obtener_almacenamiento
from app.core.clock import Reloj, ahora
from app.core.config import Configuracion, obtener_configuracion
from app.core.exceptions import (
    ErrorAlmacenamiento,
    ErrorArchivoDemasiadoGrande,
    ErrorConflicto,
    ErrorLimiteExcedido,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorProveedorExterno,
    ErrorTipoArchivo,
    ErrorValidacion,
)
from app.core.generacion_imagenes import (
    LARGO_MAX_PROMPT,
    TAMANOS_PERMITIDOS,
    PuertoGeneradorImagenes,
    exigir_generacion_disponible,
    motivo_no_disponible,
)
from app.modules.files.models import ArchivoAdjunto
from app.modules.files.repository import RepositorioArchivos

registro = logging.getLogger(__name__)

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024
CARPETA_ESCENARIOS = "escenarios"
ORIGEN_SUBIDO = "SUBIDO"
ORIGEN_IA = "GENERADO_IA"
BOGOTA = ZoneInfo("America/Bogota")

# Se reconoce el tipo por los primeros bytes del contenido (firma), no por la extensión ni por
# el Content-Type que declara el navegador, que el usuario puede falsear.
_FIRMAS = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
)

# Una generación a la vez por docente (en este proceso): evita doble clic y saltarse el tope por
# hora lanzando varias peticiones a la vez.
_generando: set[str] = set()
_candado = threading.Lock()


@contextmanager
def _una_generacion_a_la_vez(docente_id: str) -> Iterator[None]:
    with _candado:
        if docente_id in _generando:
            raise ErrorConflicto(
                "Ya tienes una imagen generándose. Espera a que termine antes de pedir otra.",
                codigo="GENERACION_EN_CURSO",
            )
        _generando.add(docente_id)
    try:
        yield
    finally:
        with _candado:
            _generando.discard(docente_id)


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
        autorizar_escenario: Callable[[str, str, dict], None] | None = None,
        fabrica_generador: Callable[[], PuertoGeneradorImagenes] | None = None,
        configuracion: Configuracion | None = None,
    ) -> None:
        self.db = db
        self.repositorio = RepositorioArchivos(db)
        self.almacenamiento = almacenamiento or obtener_almacenamiento()
        self.reloj = reloj
        # Lo que sabe el módulo de casos (quién usa un archivo, quién es dueño de un escenario) se
        # inyecta para no acoplar módulos.
        self.esta_en_uso = esta_en_uso
        self.autorizar_escenario = autorizar_escenario
        self.fabrica_generador = fabrica_generador
        self._configuracion = configuracion

    @property
    def configuracion(self) -> Configuracion:
        return self._configuracion or obtener_configuracion()

    def url(self, archivo: ArchivoAdjunto) -> str:
        return self.almacenamiento.url_publica(archivo.ruta_almacenamiento)

    def subir(
        self,
        sesion: dict,
        nombre_original: str | None,
        contenido: bytes,
        origen: str = ORIGEN_SUBIDO,
        prompt_generacion: str | None = None,
    ) -> ArchivoAdjunto:
        """Guarda el archivo y su fila como una sola unidad: si algo falla, no queda nada a medias.

        Orden: primero el archivo, luego la fila. Si la fila falla (o el commit), se borra el
        archivo; si el guardado falla, no se llega a crear la fila. Así no hay archivos huérfanos
        ni filas sin archivo. El `commit` de la fila es el último paso.
        """
        if not contenido:
            raise ErrorValidacion("El archivo está vacío")
        if len(contenido) > TAMANO_MAXIMO_BYTES:
            raise ErrorArchivoDemasiadoGrande(
                "La imagen supera el máximo de 5 MB. Reduce su tamaño e inténtalo de nuevo.",
                detalles={"maximo_bytes": TAMANO_MAXIMO_BYTES},
            )
        tipo_mime, extension = detectar_tipo(contenido)
        nombre_guardado = f"{CARPETA_ESCENARIOS}/{uuid.uuid4()}.{extension}"
        try:
            ruta = self.almacenamiento.guardar(contenido, nombre_guardado, tipo_mime)
        except Exception as error:
            self._borrar_fisico(nombre_guardado)  # por si el guardado dejó algo a medias
            registro.exception("No se pudo guardar el archivo %s", nombre_guardado)
            raise ErrorAlmacenamiento(
                "No se pudo guardar la imagen en el servidor. Inténtalo de nuevo."
            ) from error
        try:
            archivo = self.repositorio.agregar(
                ArchivoAdjunto(
                    docente_id=sesion["sub"],
                    nombre_original=_nombre_limpio(nombre_original),
                    tipo_mime=tipo_mime,
                    tamano_bytes=len(contenido),
                    ruta_almacenamiento=ruta,
                    origen=origen,
                    prompt_generacion=prompt_generacion,
                    creado_en=ahora(self.reloj),
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            self._borrar_fisico(ruta)
            raise
        return archivo

    # --- generación con IA -------------------------------------------------------------

    def _ventana_de_la_hora(self):
        inicio = ahora(self.reloj).replace(minute=0, second=0, microsecond=0)
        return inicio, inicio + timedelta(hours=1)

    def _restantes(self, docente_id: str) -> int:
        inicio, fin = self._ventana_de_la_hora()
        usadas = self.repositorio.contar_generadas(docente_id, inicio, fin)
        return max(self.configuracion.generacion_max_por_hora - usadas, 0)

    def estado_generacion(self, sesion: dict) -> dict:
        return {
            "disponible": motivo_no_disponible(self.configuracion) is None,
            "motivo": motivo_no_disponible(self.configuracion),
            "max_por_hora": self.configuracion.generacion_max_por_hora,
            "restantes": self._restantes(sesion["sub"]),
            "largo_max_prompt": LARGO_MAX_PROMPT,
            "tamanos": [
                {
                    "valor": valor,
                    "ancho": ancho,
                    "alto": alto,
                    "etiqueta": {
                        "1024x1024": "Cuadrada",
                        "1536x1024": "Horizontal",
                        "1024x1536": "Vertical",
                    }[valor],
                }
                for valor, (ancho, alto) in TAMANOS_PERMITIDOS.items()
            ],
        }

    def generar_imagen(
        self, sesion: dict, caso_id: str, escenario_id: str, prompt: str, tamano: str
    ) -> ArchivoAdjunto:
        """Genera una imagen con IA para un escenario y la registra como archivo del docente."""
        prompt = (prompt or "").strip()
        if not 1 <= len(prompt) <= LARGO_MAX_PROMPT:
            raise ErrorValidacion(
                f"La descripción debe tener entre 1 y {LARGO_MAX_PROMPT} caracteres"
            )
        if tamano not in TAMANOS_PERMITIDOS:
            raise ErrorValidacion(
                "Tamaño no permitido",
                detalles={"permitidos": list(TAMANOS_PERMITIDOS)},
            )
        # 1) permisos (dueño del caso, caso en borrador) antes de revelar el estado del servicio
        if self.autorizar_escenario is None or self.fabrica_generador is None:
            raise RuntimeError("ServicioArchivos sin la configuración necesaria para generar")
        self.autorizar_escenario(caso_id, escenario_id, sesion)
        # 2) función activa y con clave
        exigir_generacion_disponible(self.configuracion)

        docente_id = sesion["sub"]
        with _una_generacion_a_la_vez(docente_id):
            # 3) tope por docente y por hora de reloj
            if self._restantes(docente_id) == 0:
                _, fin = self._ventana_de_la_hora()
                hora = fin.astimezone(BOGOTA).strftime("%H:%M")
                raise ErrorLimiteExcedido(
                    f"Ya generaste {self.configuracion.generacion_max_por_hora} imágenes en esta "
                    f"hora. Podrás generar otra a las {hora} (hora de Bogotá).",
                    codigo="LIMITE_GENERACION_ALCANZADO",
                    detalles={
                        "max_por_hora": self.configuracion.generacion_max_por_hora,
                        "reintentar_a": fin.isoformat(),
                    },
                )
            # 4) generar y guardar. Si generar falla no se escribe nada; si guardar falla,
            #    `subir` limpia lo que haya escrito. Nada queda a medias.
            ancho, alto = TAMANOS_PERMITIDOS[tamano]
            contenido = self.fabrica_generador().generar(prompt, ancho, alto)
            try:
                return self.subir(
                    sesion,
                    "Imagen generada con IA",
                    contenido,
                    origen=ORIGEN_IA,
                    prompt_generacion=prompt,
                )
            except (ErrorTipoArchivo, ErrorArchivoDemasiadoGrande) as error:
                raise ErrorProveedorExterno(
                    "El servicio de imágenes devolvió un archivo que no se puede usar "
                    "(formato o tamaño). Inténtalo de nuevo.",
                    codigo="PROVEEDOR_IMAGENES_RESPUESTA_INVALIDA",
                ) from error

    # --- galería ------------------------------------------------------------------------

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
