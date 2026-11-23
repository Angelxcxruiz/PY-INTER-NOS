import pytest

PAGINAS = ["/app/", "/app/docente", "/app/simulador", "/app/resultado"]
ESTATICOS = [
    "estilos.css",
    "ui.js",
    "api.js",
    "login.js",
    "docente.js",
    "simulador.js",
    "resultado.js",
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


def test_la_interfaz_no_se_publica_en_swagger(cliente) -> None:
    rutas = cliente.get("/openapi.json").json()["paths"]

    assert not any(ruta.startswith("/app") for ruta in rutas)
