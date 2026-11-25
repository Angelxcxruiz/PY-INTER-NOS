import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parent.parent / "frontend" / "static" / "estilos.css"

PAGINAS = ["/app/", "/app/docente", "/app/simulador", "/app/resultado", "/app/registro"]
ESTATICOS = [
    "estilos.css",
    "ui.js",
    "api.js",
    "login.js",
    "registro.js",
    "docente.js",
    "docente_casos.js",
    "docente_puzzles.js",
    "docente_editor_visual.js",
    "composicion.js",
    "iconos/persona.svg",
    "puzzles.js",
    "docente_resultados.js",
    "simulador.js",
    "resultado.js",
    "favicon.svg",
    "logo-simbolo.svg",
]


def test_la_raiz_redirige_a_la_interfaz(cliente) -> None:
    respuesta = cliente.get("/", follow_redirects=False)

    assert respuesta.status_code in (302, 307)
    assert respuesta.headers["location"] == "/app/"


@pytest.mark.parametrize("ruta", PAGINAS)
def test_las_paginas_se_sirven_en_html_y_en_espanol(cliente, ruta) -> None:
    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/html")
    assert '<html lang="es">' in respuesta.text
    assert "/app/static/api.js" in respuesta.text


@pytest.mark.parametrize("archivo", ESTATICOS)
def test_los_archivos_estaticos_se_sirven(cliente, archivo) -> None:
    assert cliente.get(f"/app/static/{archivo}").status_code == 200


def test_los_colores_solo_se_definen_en_root() -> None:
    """Todo color del CSS sale de una variable de :root: ni hex ni rgb() con números sueltos."""
    css = CSS.read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    inicio = css.index(":root")
    fin = css.index("\n}", inicio) + 2
    fuera = css[:inicio] + css[fin:]

    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", fuera) == []
    assert re.findall(r"rgba?\(\s*\d", fuera) == []


def test_la_interfaz_declara_favicon_y_las_dos_familias_de_la_paleta(cliente) -> None:
    html = cliente.get("/app/").text
    css = CSS.read_text(encoding="utf-8")

    assert 'rel="icon"' in html and "/app/static/favicon.svg" in html
    for variable in ("--degradado-calido", "--degradado-frio", "--sobre-acento", "--sobre-frio"):
        assert variable in css


def test_la_interfaz_no_se_publica_en_swagger(cliente) -> None:
    rutas = cliente.get("/openapi.json").json()["paths"]

    assert not any(ruta.startswith("/app") for ruta in rutas)
