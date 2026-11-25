"""Generación de imágenes con IA detrás de un puerto (Fase 15).

Ningún módulo llama a Google directamente: pide un `PuertoGeneradorImagenes`. `AdaptadorGemini` usa
la API REST de Gemini con `httpx` (sin SDK). La clave de API se envía solo en el encabezado
`x-goog-api-key`: no va en la URL, ni en los logs, ni en ningún mensaje de error.
"""

import base64
import logging
from typing import Protocol

import httpx

from app.core.config import MARCADOR_SECRETO, Configuracion, obtener_configuracion
from app.core.exceptions import (
    ErrorLimiteExcedido,
    ErrorProveedorExterno,
    ErrorServicioNoDisponible,
    ErrorTiempoAgotado,
    ErrorValidacion,
)

registro = logging.getLogger(__name__)

URL_BASE_GEMINI = "https://generativelanguage.googleapis.com/v1beta"

# Tres tamaños fijos (ancho, alto) -> relación de aspecto que entiende el proveedor. No se aceptan
# medidas libres: el proveedor las rechazaría.
TAMANOS_PERMITIDOS: dict[str, tuple[int, int]] = {
    "1024x1024": (1024, 1024),
    "1536x1024": (1536, 1024),
    "1024x1536": (1024, 1536),
}
_RELACIONES = {(1024, 1024): "1:1", (1536, 1024): "3:2", (1024, 1536): "2:3"}
LARGO_MAX_PROMPT = 500

_BLOQUEOS = ("BLOCKLIST", "SPII", "RECITATION", "LANGUAGE")
_PALABRAS_BLOQUEO = ("safety", "blocked", "policy", "prohibited")

MENSAJE_PROMPT_RECHAZADO = (
    "El servicio de imágenes rechazó la descripción por sus políticas de contenido. "
    "Reformúlala con otras palabras e inténtalo de nuevo."
)


class PuertoGeneradorImagenes(Protocol):
    def generar(self, prompt: str, ancho: int, alto: int) -> bytes:
        """Devuelve los bytes de la imagen generada (PNG o JPEG)."""
        ...


def _bloqueada_por_contenido(motivo: str | None) -> bool:
    texto = (motivo or "").upper()
    return "SAFETY" in texto or "PROHIBITED" in texto or texto in _BLOQUEOS


def _extraer_imagen(datos: dict) -> bytes:
    """Busca la primera imagen de la respuesta; sin imagen, explica por qué no la hay."""
    for candidato in datos.get("candidates") or []:
        for parte in (candidato.get("content") or {}).get("parts") or []:
            blob = parte.get("inlineData") or parte.get("inline_data") or {}
            if blob.get("data"):
                try:
                    return base64.b64decode(blob["data"], validate=True)
                except ValueError as error:
                    raise ErrorProveedorExterno(
                        "El servicio de imágenes devolvió un archivo dañado. Inténtalo de nuevo.",
                        codigo="PROVEEDOR_IMAGENES_RESPUESTA_INVALIDA",
                    ) from error
    motivos = [datos.get("promptFeedback", {}).get("blockReason")]
    motivos += [candidato.get("finishReason") for candidato in datos.get("candidates") or []]
    if any(_bloqueada_por_contenido(motivo) for motivo in motivos):
        raise ErrorValidacion(MENSAJE_PROMPT_RECHAZADO, codigo="PROMPT_RECHAZADO")
    raise ErrorProveedorExterno(
        "El servicio de imágenes no devolvió ninguna imagen. Prueba con otra descripción.",
        codigo="PROVEEDOR_IMAGENES_SIN_IMAGEN",
    )


class AdaptadorGemini:
    def __init__(
        self,
        clave: str,
        modelo: str,
        timeout_seg: float,
        cliente: httpx.Client | None = None,
    ) -> None:
        self._clave = clave
        self.modelo = modelo
        self.timeout_seg = timeout_seg
        self._cliente = cliente  # inyectable: las pruebas usan un transporte simulado

    def __repr__(self) -> str:
        return f"AdaptadorGemini(modelo={self.modelo!r})"

    def generar(self, prompt: str, ancho: int, alto: int) -> bytes:
        relacion = _RELACIONES.get((ancho, alto))
        if relacion is None:
            raise ValueError(f"Tamaño no admitido: {ancho}x{alto}")
        cuerpo = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": relacion},
            },
        }
        url = f"{URL_BASE_GEMINI}/models/{self.modelo}:generateContent"
        cabeceras = {"x-goog-api-key": self._clave, "Content-Type": "application/json"}
        try:
            if self._cliente is not None:
                respuesta = self._cliente.post(
                    url, headers=cabeceras, json=cuerpo, timeout=self.timeout_seg
                )
            else:
                with httpx.Client(timeout=self.timeout_seg) as cliente:
                    respuesta = cliente.post(url, headers=cabeceras, json=cuerpo)
        except httpx.TimeoutException as error:
            raise ErrorTiempoAgotado(
                "La generación de la imagen tardó demasiado. Inténtalo de nuevo en un momento.",
                codigo="GENERACION_TIEMPO_AGOTADO",
            ) from error
        except httpx.HTTPError as error:
            # Solo el tipo de error: el texto de la excepción podría traer la URL.
            registro.warning("Gemini: fallo de red (%s)", type(error).__name__)
            raise ErrorProveedorExterno(
                "No se pudo conectar con el servicio de imágenes. Inténtalo de nuevo.",
                codigo="PROVEEDOR_IMAGENES_SIN_CONEXION",
            ) from None
        return self._interpretar(respuesta)

    def _interpretar(self, respuesta: httpx.Response) -> bytes:
        try:
            datos = respuesta.json()
        except ValueError:
            datos = {}
        if not isinstance(datos, dict):
            datos = {}
        if respuesta.status_code == 200:
            return _extraer_imagen(datos)

        error = datos.get("error") if isinstance(datos.get("error"), dict) else {}
        # Se registra solo el estado HTTP y el estado simbólico de Google; nunca el cuerpo completo.
        registro.warning(
            "Gemini respondió %s (%s)", respuesta.status_code, error.get("status", "sin estado")
        )
        if respuesta.status_code == 429:
            raise ErrorLimiteExcedido(
                "El servicio de imágenes está saturado en este momento. Espera unos minutos "
                "e inténtalo de nuevo.",
                codigo="PROVEEDOR_IMAGENES_SATURADO",
            )
        mensaje = str(error.get("message", "")).lower()
        if respuesta.status_code == 400 and (
            datos.get("promptFeedback") or any(palabra in mensaje for palabra in _PALABRAS_BLOQUEO)
        ):
            raise ErrorValidacion(MENSAJE_PROMPT_RECHAZADO, codigo="PROMPT_RECHAZADO")
        if respuesta.status_code in (401, 403, 404):
            raise ErrorProveedorExterno(
                "El servicio de imágenes no está bien configurado en el servidor (clave o modelo). "
                "Avisa al administrador.",
                codigo="PROVEEDOR_IMAGENES_CONFIGURACION",
            )
        raise ErrorProveedorExterno(
            "El servicio de imágenes falló. Inténtalo de nuevo en unos minutos.",
            codigo="PROVEEDOR_IMAGENES_ERROR",
        )


def _clave_configurada(configuracion: Configuracion) -> str:
    clave = configuracion.gemini_api_key.get_secret_value().strip()
    return "" if clave == MARCADOR_SECRETO else clave


def motivo_no_disponible(configuracion: Configuracion | None = None) -> str | None:
    """Por qué no se puede generar ahora (o None si se puede). Sin tocar la red."""
    configuracion = configuracion or obtener_configuracion()
    if not configuracion.generacion_imagenes_activa:
        return "La generación de imágenes con IA está desactivada en este servidor."
    if not _clave_configurada(configuracion):
        return (
            "La generación de imágenes con IA todavía no está configurada en el servidor. "
            "Mientras tanto puedes subir una imagen."
        )
    return None


def exigir_generacion_disponible(configuracion: Configuracion | None = None) -> None:
    motivo = motivo_no_disponible(configuracion)
    if motivo:
        raise ErrorServicioNoDisponible(motivo, codigo="GENERACION_NO_DISPONIBLE")


def construir_generador() -> PuertoGeneradorImagenes:
    configuracion = obtener_configuracion()
    exigir_generacion_disponible(configuracion)
    return AdaptadorGemini(
        _clave_configurada(configuracion),
        configuracion.gemini_modelo_imagen,
        configuracion.gemini_timeout_seg,
    )
