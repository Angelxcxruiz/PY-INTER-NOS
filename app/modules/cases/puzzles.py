"""Puzzles lógicos de cada escenario (Fase 13): contenido, vista del estudiante y verificación.

Reglas que este módulo protege:
- Un puzzle NO puntúa: nada de aquí toca la rúbrica ni la nota.
- La solución nunca sale hacia el estudiante. `vista_estudiante` devuelve los elementos
  barajados y sin solución, y `verificar` solo responde si acertó o no.

Los cuatro tipos son lógicos (sin imágenes). `contenido` guarda en la base los elementos con
su solución más `tiempo_seg` (30 a 60 s).
"""

import random
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.core.exceptions import ErrorValidacion

ORDENAR_SECUENCIA = "ORDENAR_SECUENCIA"
EMPAREJAR_CONCEPTOS = "EMPAREJAR_CONCEPTOS"
PIEZA_FALTANTE = "PIEZA_FALTANTE"
CLASIFICAR = "CLASIFICAR"

TIPOS_PUZZLE = (ORDENAR_SECUENCIA, EMPAREJAR_CONCEPTOS, PIEZA_FALTANTE, CLASIFICAR)
TipoPuzzle = Literal["ORDENAR_SECUENCIA", "EMPAREJAR_CONCEPTOS", "PIEZA_FALTANTE", "CLASIFICAR"]
MAX_PUZZLES_POR_ESCENARIO = 3
TIEMPO_POR_DEFECTO_SEG = 45

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
_azar = random.SystemRandom()


def _unicos(valores: list[str], descripcion: str) -> None:
    normalizados = [valor.casefold() for valor in valores]
    if len(set(normalizados)) != len(normalizados):
        raise ValueError(f"{descripcion} no pueden repetirse")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ContenidoBase(_Base):
    tiempo_seg: int = Field(default=TIEMPO_POR_DEFECTO_SEG, ge=30, le=60)


# --- contenido guardado (incluye la solución) -------------------------------------------


class ContenidoOrdenar(_ContenidoBase):
    """`pasos` está en el orden CORRECTO."""

    pasos: list[Texto] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def _sin_repetidos(self):
        _unicos(self.pasos, "Los pasos")
        return self


class ParConcepto(_Base):
    termino: Texto
    definicion: Texto


class ContenidoEmparejar(_ContenidoBase):
    pares: list[ParConcepto] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _sin_repetidos(self):
        _unicos([par.termino for par in self.pares], "Los términos")
        _unicos([par.definicion for par in self.pares], "Las definiciones")
        return self


class ContenidoPiezaFaltante(_ContenidoBase):
    """`serie` completa; `faltante` es la posición (desde 0) que se oculta al estudiante."""

    serie: list[Texto] = Field(min_length=3, max_length=8)
    faltante: int = Field(ge=0)
    distractores: list[Texto] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _coherente(self):
        if self.faltante >= len(self.serie):
            raise ValueError("La posición faltante debe estar dentro de la serie")
        opciones = [self.serie[self.faltante], *self.distractores]
        _unicos(opciones, "Las opciones")
        return self


class ElementoClasificable(_Base):
    texto: Texto
    categoria: Texto


class ContenidoClasificar(_ContenidoBase):
    categorias: list[Texto] = Field(min_length=2, max_length=4)
    elementos: list[ElementoClasificable] = Field(min_length=3, max_length=10)

    @model_validator(mode="after")
    def _coherente(self):
        _unicos(self.categorias, "Las categorías")
        _unicos([elemento.texto for elemento in self.elementos], "Los elementos")
        permitidas = {categoria.casefold() for categoria in self.categorias}
        usadas = set()
        for elemento in self.elementos:
            if elemento.categoria.casefold() not in permitidas:
                raise ValueError("Cada elemento debe pertenecer a una de las categorías")
            usadas.add(elemento.categoria.casefold())
        if usadas != permitidas:
            raise ValueError("Cada categoría necesita al menos un elemento")
        return self


MODELOS_CONTENIDO: dict[str, type[_ContenidoBase]] = {
    ORDENAR_SECUENCIA: ContenidoOrdenar,
    EMPAREJAR_CONCEPTOS: ContenidoEmparejar,
    PIEZA_FALTANTE: ContenidoPiezaFaltante,
    CLASIFICAR: ContenidoClasificar,
}


def validar_contenido(tipo: str, contenido: dict) -> dict:
    """Valida el contenido según el tipo y devuelve el dict normalizado que se guarda."""
    modelo = MODELOS_CONTENIDO.get(tipo)
    if modelo is None:
        raise ErrorValidacion("Tipo de puzzle no permitido", detalles={"tipos": list(TIPOS_PUZZLE)})
    try:
        return modelo.model_validate(contenido).model_dump()
    except ValidationError as error:
        primero = error.errors(include_url=False, include_context=False, include_input=False)[0]
        campo = ".".join(str(parte) for parte in primero["loc"])
        mensaje = primero["msg"].removeprefix("Value error, ")
        raise ErrorValidacion(
            f"Contenido del puzzle inválido: {mensaje}",
            detalles={"campo": campo},
        ) from error


# --- vista del estudiante (barajada y SIN solución) -------------------------------------


def _barajar(valores: list, evitar: list | None = None) -> list:
    """Baraja una copia; si `evitar` es el orden que no debe quedar, reintenta."""
    copia = list(valores)
    for _ in range(25):
        _azar.shuffle(copia)
        if evitar is None or len(copia) < 2 or copia != evitar:
            return copia
    copia[0], copia[1] = copia[1], copia[0]
    return copia


def vista_estudiante(tipo: str, contenido: dict) -> tuple[int, dict]:
    """Devuelve (tiempo_seg, datos) con lo único que puede ver quien va a jugar el puzzle."""
    tiempo = int(contenido.get("tiempo_seg", TIEMPO_POR_DEFECTO_SEG))
    if tipo == ORDENAR_SECUENCIA:
        pasos = contenido["pasos"]
        return tiempo, {"elementos": _barajar(pasos, evitar=pasos)}
    if tipo == EMPAREJAR_CONCEPTOS:
        terminos = [par["termino"] for par in contenido["pares"]]
        definiciones = [par["definicion"] for par in contenido["pares"]]
        return tiempo, {
            "terminos": _barajar(terminos),
            "definiciones": _barajar(definiciones, evitar=definiciones),
        }
    if tipo == PIEZA_FALTANTE:
        serie = list(contenido["serie"])
        correcta = serie[contenido["faltante"]]
        serie[contenido["faltante"]] = None
        return tiempo, {
            "serie": serie,
            "opciones": _barajar([correcta, *contenido["distractores"]]),
        }
    if tipo == CLASIFICAR:
        textos = [elemento["texto"] for elemento in contenido["elementos"]]
        return tiempo, {"categorias": list(contenido["categorias"]), "elementos": _barajar(textos)}
    raise ErrorValidacion("Tipo de puzzle no permitido")


# --- verificación (solo dice si acertó) -------------------------------------------------


class _RespuestaOrdenar(_Base):
    orden: list[str]


class _ParRespuesta(_Base):
    termino: str
    definicion: str


class _RespuestaEmparejar(_Base):
    pares: list[_ParRespuesta]


class _RespuestaPieza(_Base):
    opcion: str


class _Asignacion(_Base):
    texto: str
    categoria: str


class _RespuestaClasificar(_Base):
    asignaciones: list[_Asignacion]


def _n(texto: str) -> str:
    return texto.strip().casefold()


def verificar(tipo: str, contenido: dict, respuesta: dict) -> bool:
    """True solo si la respuesta coincide con la solución. Nunca devuelve la solución."""
    try:
        if tipo == ORDENAR_SECUENCIA:
            dada = _RespuestaOrdenar.model_validate(respuesta)
            return [_n(p) for p in dada.orden] == [_n(p) for p in contenido["pasos"]]
        if tipo == EMPAREJAR_CONCEPTOS:
            dada = _RespuestaEmparejar.model_validate(respuesta)
            esperado = {_n(par["termino"]): _n(par["definicion"]) for par in contenido["pares"]}
            recibido = {_n(par.termino): _n(par.definicion) for par in dada.pares}
            return len(dada.pares) == len(esperado) and recibido == esperado
        if tipo == PIEZA_FALTANTE:
            dada = _RespuestaPieza.model_validate(respuesta)
            return _n(dada.opcion) == _n(contenido["serie"][contenido["faltante"]])
        if tipo == CLASIFICAR:
            dada = _RespuestaClasificar.model_validate(respuesta)
            esperado = {_n(e["texto"]): _n(e["categoria"]) for e in contenido["elementos"]}
            recibido = {_n(a.texto): _n(a.categoria) for a in dada.asignaciones}
            return len(dada.asignaciones) == len(esperado) and recibido == esperado
    except ValidationError as error:
        raise ErrorValidacion("La respuesta del puzzle no tiene el formato esperado") from error
    raise ErrorValidacion("Tipo de puzzle no permitido")
