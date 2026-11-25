"""Editor visual de escenarios (Fase 14): composiciones, archivos subidos y almacenamiento."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from ayudas_editor import _cabeceras
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text

from app.core.almacenamiento import (
    AlmacenamientoLocal,
    AlmacenamientoS3,
    directorio_media,
    obtener_almacenamiento,
)
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.exceptions import ErrorTipoArchivo
from app.modules.cases.composicion import ICONOS_PERMITIDOS
from app.modules.cases.models import Caso, ComposicionEscenario
from app.modules.cases.schemas_composicion import ComposicionEntrada
from app.modules.files.service import TAMANO_MAXIMO_BYTES, detectar_tipo

RAIZ = Path(__file__).resolve().parent.parent
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64


def _id() -> str:
    return str(uuid.uuid4())


def _capa_texto(**extra) -> dict:
    return {"tipo": "texto", "id": "t1", "contenido": "Hola", **extra}


# --- unidades: tipo de archivo, almacenamiento y validación de capas ---------------------


def test_el_tipo_se_reconoce_por_el_contenido_y_no_por_la_extension() -> None:
    assert detectar_tipo(PNG) == ("image/png", "png")
    assert detectar_tipo(JPG) == ("image/jpeg", "jpg")
    for falso in (GIF, b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"MZ" + b"\x00" * 20):
        with pytest.raises(ErrorTipoArchivo):
            detectar_tipo(falso)


def test_almacenamiento_local_guarda_sirve_y_elimina(tmp_path) -> None:
    almacenamiento = AlmacenamientoLocal(tmp_path)

    ruta = almacenamiento.guardar(PNG, "escenarios/a.png", "image/png")

    assert ruta == "escenarios/a.png"
    assert (tmp_path / "escenarios" / "a.png").read_bytes() == PNG
    assert almacenamiento.url_publica(ruta) == "/media/escenarios/a.png"
    almacenamiento.eliminar(ruta)
    almacenamiento.eliminar(ruta)  # borrar dos veces no es un error
    assert not (tmp_path / "escenarios" / "a.png").exists()


@pytest.mark.parametrize("ruta", ["../fuera.png", "escenarios/../../fuera.png", "/etc/passwd", ""])
def test_almacenamiento_local_no_escribe_fuera_de_su_carpeta(tmp_path, ruta) -> None:
    with pytest.raises(ValueError):
        AlmacenamientoLocal(tmp_path / "uploads").guardar(PNG, ruta, "image/png")


def test_almacenamiento_s3_esta_reservado_y_no_envia_nada() -> None:
    s3 = AlmacenamientoS3()
    with pytest.raises(NotImplementedError):
        s3.guardar(PNG, "escenarios/a.png", "image/png")
    with pytest.raises(NotImplementedError):
        s3.url_publica("escenarios/a.png")
    with pytest.raises(NotImplementedError):
        s3.eliminar("escenarios/a.png")


def test_la_configuracion_elige_el_almacenamiento(monkeypatch) -> None:
    configuracion = obtener_configuracion()
    assert isinstance(obtener_almacenamiento(), AlmacenamientoLocal)
    monkeypatch.setattr(configuracion, "almacenamiento_backend", "s3")
    assert isinstance(obtener_almacenamiento(), AlmacenamientoS3)


def test_cada_icono_del_conjunto_tiene_su_archivo_svg() -> None:
    carpeta = RAIZ / "frontend" / "static" / "iconos"
    archivos = {archivo.stem for archivo in carpeta.glob("*.svg")}
    assert archivos == set(ICONOS_PERMITIDOS)


def test_el_proyecto_no_usa_el_nombre_de_marcas_ajenas() -> None:
    """La funcionalidad se llama «editor visual de escenarios»; no se nombra con una marca."""
    marca = "can" + "va"
    revisados = 0
    for carpeta in ("app", "frontend", "docs", "tests", "alembic", "scripts"):
        for archivo in (RAIZ / carpeta).rglob("*"):
            if not archivo.is_file() or archivo.suffix not in {
                ".py",
                ".js",
                ".css",
                ".html",
                ".md",
            }:
                continue
            revisados += 1
            assert marca not in archivo.read_text(encoding="utf-8").lower(), archivo
    assert revisados > 50


def test_la_composicion_renumera_el_orden_y_conserva_las_capas() -> None:
    composicion = ComposicionEntrada.model_validate(
        {
            "capas": [
                _capa_texto(id="arriba", orden=9),
                _capa_texto(id="abajo", orden=2),
                _capa_texto(id="empate", orden=2),
            ]
        }
    )
    assert [(c.id, c.orden) for c in composicion.capas] == [
        ("abajo", 1),
        ("empate", 2),
        ("arriba", 3),
    ]
    assert (composicion.ancho, composicion.alto) == (1280, 720)


@pytest.mark.parametrize(
    "capas",
    [
        [_capa_texto(id="a"), _capa_texto(id="a")],  # ids repetidos
        [_capa_texto(color="rojo")],  # color no hexadecimal
        [_capa_texto(alineacion="arriba")],
        [_capa_texto(tamano=2)],
        [{"tipo": "icono", "id": "i", "icono": "calavera"}],  # fuera del conjunto fijo
        [{"tipo": "forma", "id": "f", "forma": "triangulo"}],
        [{"tipo": "forma", "id": "f", "forma": "circulo", "opacidad": 2}],
        [{"tipo": "video", "id": "v"}],
        [_capa_texto(extra="no permitido")],
    ],
)
def test_la_composicion_rechaza_capas_invalidas(capas) -> None:
    with pytest.raises(ValidationError):
        ComposicionEntrada.model_validate({"capas": capas})


def test_la_composicion_rechaza_mas_de_sesenta_capas() -> None:
    capas = [_capa_texto(id=f"c{i}") for i in range(61)]
    with pytest.raises(ValidationError):
        ComposicionEntrada.model_validate({"capas": capas})


# --- integración contra MySQL real (fixtures `db` y `taller` en conftest.py) ---------------


def _subir(cliente, cabeceras, contenido=PNG, nombre="fondo.png", tipo="image/png"):
    return cliente.post(
        "/api/v1/archivos/escenarios",
        headers=cabeceras,
        files={"archivo": (nombre, contenido, tipo)},
    )


def _ruta_composicion(taller, indice=0) -> str:
    return (
        f"/api/v1/cases/{taller['caso_id']}/escenarios/{taller['escenarios'][indice]}/composicion"
    )


def _composicion(archivo_id: str, **extra) -> dict:
    return {
        "ancho": 1280,
        "alto": 720,
        "fondo_color": "#0b0c2b",
        "capas": [
            {
                "tipo": "texto",
                "id": "titulo",
                "orden": 3,
                "x": 80,
                "y": 60,
                "ancho": 600,
                "contenido": "El pasillo",
                "tamano": 64,
                "color": "#fbbf24",
                "alineacion": "centro",
                "negrita": True,
                "cursiva": True,
            },
            {
                "tipo": "imagen",
                "id": "fondo",
                "orden": 1,
                "archivo_id": archivo_id,
                "url": "http://malicioso.example/x.png",
                "ajuste": "cubrir",
                "x": 0,
                "y": 0,
                "ancho": 1280,
                "alto": 720,
            },
            {
                "tipo": "forma",
                "id": "panel",
                "orden": 2,
                "forma": "rectangulo_redondeado",
                "relleno": "#14b8a6",
                "borde_color": "#22d3ee",
                "borde_grosor": 4,
                "opacidad": 0.5,
                "x": 60,
                "y": 40,
                "ancho": 700,
                "alto": 140,
            },
            {
                "tipo": "icono",
                "id": "ojo",
                "orden": 4,
                "icono": "ojo",
                "x": 900,
                "y": 80,
                "ancho": 96,
            },
        ],
        **extra,
    }


def test_subir_una_imagen_la_guarda_y_la_sirve_en_media(cliente, taller) -> None:
    respuesta = _subir(cliente, taller["cabeceras"])

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo_mime"] == "image/png" and cuerpo["tamano_bytes"] == len(PNG)
    assert cuerpo["nombre_original"] == "fondo.png"
    assert cuerpo["url"].startswith("/media/escenarios/") and cuerpo["url"].endswith(".png")
    servido = cliente.get(cuerpo["url"])
    assert servido.status_code == 200 and servido.content == PNG
    listado = cliente.get("/api/v1/archivos", headers=taller["cabeceras"]).json()
    assert [a["id"] for a in listado] == [cuerpo["id"]]
    assert cliente.get("/api/v1/archivos", headers=taller["otro"]).json() == []


def test_una_imagen_jpg_se_acepta_aunque_la_extension_sea_otra(cliente, taller) -> None:
    respuesta = _subir(cliente, taller["cabeceras"], JPG, "foto.dat", "application/octet-stream")

    assert respuesta.status_code == 201
    assert respuesta.json()["tipo_mime"] == "image/jpeg"
    assert respuesta.json()["url"].endswith(".jpg")


def test_el_nombre_original_no_viaja_a_la_ruta_del_disco(cliente, taller) -> None:
    respuesta = _subir(cliente, taller["cabeceras"], PNG, "..\\..\\secreto.png")

    assert respuesta.status_code == 201
    assert respuesta.json()["nombre_original"] == "secreto.png"
    assert ".." not in respuesta.json()["url"] and "secreto" not in respuesta.json()["url"]


def test_subir_valida_tamano_y_tipo_real(cliente, taller) -> None:
    grande = _subir(cliente, taller["cabeceras"], PNG + b"0" * TAMANO_MAXIMO_BYTES)
    disfrazado = _subir(cliente, taller["cabeceras"], GIF, "inocente.png", "image/png")
    texto = _subir(
        cliente, taller["cabeceras"], b"<script>alert(1)</script>", "a.jpg", "image/jpeg"
    )
    vacio = _subir(cliente, taller["cabeceras"], b"")

    assert grande.status_code == 413
    assert grande.json()["error"]["codigo"] == "ARCHIVO_DEMASIADO_GRANDE"
    assert "5 MB" in grande.json()["error"]["mensaje"]
    assert disfrazado.status_code == 415 and texto.status_code == 415
    assert disfrazado.json()["error"]["codigo"] == "TIPO_ARCHIVO_NO_PERMITIDO"
    assert vacio.status_code == 422


def test_un_archivo_justo_en_el_limite_se_acepta(cliente, taller) -> None:
    justo = PNG + b"0" * (TAMANO_MAXIMO_BYTES - len(PNG))
    assert len(justo) == TAMANO_MAXIMO_BYTES
    assert _subir(cliente, taller["cabeceras"], justo).status_code == 201


def test_subir_exige_sesion_y_permiso(cliente, taller) -> None:
    sin_sesion = cliente.post("/api/v1/archivos/escenarios", files={"archivo": ("a.png", PNG)})
    estudiante = _subir(cliente, _cabeceras(_id(), "ESTUDIANTE", permisos=()))

    assert sin_sesion.status_code == 401
    assert estudiante.status_code == 401  # sin el permiso CREAR_CASOS (así responde el proyecto)


def test_guardar_la_composicion_pone_la_url_en_el_servidor_y_renumera(cliente, db, taller) -> None:
    archivo = _subir(cliente, taller["cabeceras"]).json()

    respuesta = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(archivo["id"])
    )

    assert respuesta.status_code == 200, respuesta.text
    capas = respuesta.json()["capas"]
    assert [(c["id"], c["orden"]) for c in capas] == [
        ("fondo", 1),
        ("panel", 2),
        ("titulo", 3),
        ("ojo", 4),
    ]
    imagen = capas[0]
    assert imagen["url"] == archivo["url"] and "malicioso" not in respuesta.text
    leida = cliente.get(_ruta_composicion(taller), headers=taller["cabeceras"])
    assert leida.status_code == 200 and leida.json()["capas"] == capas
    assert cliente.get(_ruta_composicion(taller, 1), headers=taller["cabeceras"]).json() is None
    assert db.scalar(select(func.count()).select_from(ComposicionEscenario)) >= 1


def test_guardar_otra_vez_reemplaza_la_composicion_sin_historial(cliente, db, taller) -> None:
    archivo = _subir(cliente, taller["cabeceras"]).json()
    primera = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(archivo["id"])
    ).json()

    segunda = cliente.put(
        _ruta_composicion(taller),
        headers=taller["cabeceras"],
        json={"ancho": 800, "alto": 450, "fondo_color": "#171a4d", "capas": [_capa_texto()]},
    )

    assert segunda.status_code == 200
    assert segunda.json()["id"] == primera["id"]
    assert (segunda.json()["ancho"], len(segunda.json()["capas"])) == (800, 1)
    filas = db.scalar(
        select(func.count())
        .select_from(ComposicionEscenario)
        .where(ComposicionEscenario.escenario_id == taller["escenarios"][0])
    )
    assert filas == 1


def test_la_composicion_rechaza_imagenes_inexistentes_o_ajenas(cliente, taller) -> None:
    ajena = _subir(cliente, taller["otro"]).json()

    inexistente = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(_id())
    )
    de_otro = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(ajena["id"])
    )

    assert inexistente.status_code == 422 and de_otro.status_code == 422
    invalida = cliente.put(
        _ruta_composicion(taller),
        headers=taller["cabeceras"],
        json={"capas": [{"tipo": "icono", "id": "x", "icono": "calavera"}]},
    )
    assert invalida.status_code == 422
    assert invalida.json()["error"]["codigo"] == "VALIDACION_FALLIDA"
    assert "Icono no disponible" in invalida.text


def test_solo_el_docente_dueno_edita_la_composicion(cliente, taller) -> None:
    ajena = cliente.put(_ruta_composicion(taller), headers=taller["otro"], json={"capas": []})
    sin_sesion = cliente.put(_ruta_composicion(taller), json={"capas": []})
    inexistente = cliente.put(
        f"/api/v1/cases/{taller['caso_id']}/escenarios/{_id()}/composicion",
        headers=taller["cabeceras"],
        json={"capas": []},
    )

    assert (ajena.status_code, sin_sesion.status_code, inexistente.status_code) == (403, 401, 404)
    assert cliente.get(_ruta_composicion(taller), headers=taller["otro"]).status_code == 403


def test_un_caso_publicado_no_admite_cambios_en_la_composicion(cliente, db, taller) -> None:
    cliente.put(_ruta_composicion(taller), headers=taller["cabeceras"], json={"capas": []})
    db.execute(
        text("UPDATE caso SET estado = 'PUBLICADO' WHERE id = :id"), {"id": taller["caso_id"]}
    )
    db.commit()

    guardar = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json={"capas": [_capa_texto()]}
    )
    borrar = cliente.delete(_ruta_composicion(taller), headers=taller["cabeceras"])

    assert guardar.status_code == 409 and borrar.status_code == 409


def test_el_estudiante_recibe_la_composicion_anidada_o_null(cliente, db, taller) -> None:
    archivo = _subir(cliente, taller["cabeceras"]).json()
    cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(archivo["id"])
    )
    db.execute(
        text("UPDATE caso SET estado = 'PUBLICADO' WHERE id = :id"), {"id": taller["caso_id"]}
    )
    db.commit()

    vista = cliente.get(f"/api/v1/cases/{taller['caso_id']}/vista-estudiante")

    assert vista.status_code == 200, vista.text
    primero, segundo = vista.json()["escenarios"]
    assert segundo["composicion"] is None
    composicion = primero["composicion"]
    assert set(composicion) == {"ancho", "alto", "fondo_color", "capas"}
    assert composicion["capas"][0]["url"] == archivo["url"]
    assert composicion["capas"][0]["tipo"] == "imagen"


def test_new_version_copia_la_composicion(cliente, db, taller) -> None:
    archivo = _subir(cliente, taller["cabeceras"]).json()
    original = cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(archivo["id"])
    ).json()

    nueva = cliente.post(
        f"/api/v1/cases/{taller['caso_id']}/new-version", headers=taller["cabeceras"]
    )

    try:
        assert nueva.status_code == 200, nueva.text
        copiado = nueva.json()["escenarios"][0]["composicion"]
        assert copiado["id"] != original["id"]
        assert copiado["capas"] == original["capas"]
        assert copiado["fondo_color"] == original["fondo_color"]
        assert nueva.json()["escenarios"][1]["composicion"] is None
    finally:
        db.rollback()
        db.execute(delete(Caso).where(Caso.id == nueva.json()["id"]))
        db.commit()


def test_eliminar_la_composicion_deja_el_escenario_sin_ella(cliente, taller) -> None:
    cliente.put(_ruta_composicion(taller), headers=taller["cabeceras"], json={"capas": []})

    borrada = cliente.delete(_ruta_composicion(taller), headers=taller["cabeceras"])

    assert borrada.status_code == 204
    assert cliente.get(_ruta_composicion(taller), headers=taller["cabeceras"]).json() is None
    assert cliente.delete(_ruta_composicion(taller), headers=taller["cabeceras"]).status_code == 404


def test_borrar_una_imagen_en_uso_da_409_y_libre_se_borra_del_disco(cliente, taller) -> None:
    archivo = _subir(cliente, taller["cabeceras"]).json()
    cliente.put(
        _ruta_composicion(taller), headers=taller["cabeceras"], json=_composicion(archivo["id"])
    )
    ruta = f"/api/v1/archivos/{archivo['id']}"
    en_disco = directorio_media() / archivo["url"].removeprefix("/media/")

    en_uso = cliente.delete(ruta, headers=taller["cabeceras"])
    ajeno = cliente.delete(ruta, headers=taller["otro"])
    assert en_uso.status_code == 409 and ajeno.status_code == 403 and en_disco.exists()

    cliente.delete(_ruta_composicion(taller), headers=taller["cabeceras"])
    libre = cliente.delete(ruta, headers=taller["cabeceras"])

    assert libre.status_code == 204 and not en_disco.exists()
    assert cliente.get(archivo["url"]).status_code == 404
    assert cliente.delete(ruta, headers=taller["cabeceras"]).status_code == 404


# --- migración -----------------------------------------------------------------------------


def _alembic(*argumentos: str) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=RAIZ,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert resultado.returncode == 0, resultado.stderr


def _tablas() -> set[str]:
    with SessionLocal() as sesion:
        filas = sesion.execute(
            text(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME IN ('composicion_escenario', 'archivo_adjunto')"
            )
        ).all()
    return {fila[0] for fila in filas}


def test_la_migracion_de_composiciones_baja_a_0013_y_vuelve_a_subir(base_real) -> None:
    assert _tablas() == {"composicion_escenario", "archivo_adjunto"}
    try:
        _alembic("downgrade", "0013_puzzles")
        assert _tablas() == set()
    finally:
        _alembic("upgrade", "head")
    assert _tablas() == {"composicion_escenario", "archivo_adjunto"}
