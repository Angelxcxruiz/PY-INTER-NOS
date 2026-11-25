"""Generación de imágenes con IA (Fase 15). Nunca se llama a Google: generador falso y transporte
HTTP simulado."""

import base64
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from ayudas_editor import _cabeceras
from sqlalchemy import delete, func, select, text
from test_composiciones import JPG, PNG, RAIZ, _composicion, _subir

from app.core.almacenamiento import AlmacenamientoLocal, directorio_media
from app.core.config import Configuracion, obtener_configuracion
from app.core.database import SessionLocal
from app.core.exceptions import (
    ErrorLimiteExcedido,
    ErrorProveedorExterno,
    ErrorTiempoAgotado,
    ErrorValidacion,
)
from app.core.generacion_imagenes import AdaptadorGemini, motivo_no_disponible
from app.main import app
from app.modules.files.dependencies import obtener_fabrica_generador
from app.modules.files.models import ArchivoAdjunto
from app.modules.files.service import ServicioArchivos, _generando

CLAVE = os.environ["GEMINI_API_KEY"]
RUTA_GENERAR = "/api/v1/archivos/generar"


class GeneradorFalso:
    def __init__(self, contenido: bytes = PNG, error: Exception | None = None) -> None:
        self.contenido = contenido
        self.error = error
        self.llamadas: list[tuple[str, int, int]] = []

    def generar(self, prompt: str, ancho: int, alto: int) -> bytes:
        self.llamadas.append((prompt, ancho, alto))
        if self.error is not None:
            raise self.error
        return self.contenido


@pytest.fixture
def generador():
    falso = GeneradorFalso()
    app.dependency_overrides[obtener_fabrica_generador] = lambda: lambda: falso
    yield falso
    app.dependency_overrides.pop(obtener_fabrica_generador, None)


def _generar(cliente, taller, prompt="Un pasillo vacío de la facultad", cabeceras=None, **extra):
    cuerpo = {
        "caso_id": taller["caso_id"],
        "escenario_id": taller["escenarios"][0],
        "prompt": prompt,
        **extra,
    }
    return cliente.post(RUTA_GENERAR, headers=cabeceras or taller["cabeceras"], json=cuerpo)


def _filas(db, docente_id: str) -> int:
    db.rollback()  # ver lo ya confirmado por otras sesiones
    return db.scalar(
        select(func.count())
        .select_from(ArchivoAdjunto)
        .where(ArchivoAdjunto.docente_id == docente_id)
    )


def _archivos_en_disco() -> set[str]:
    return {str(p) for p in (directorio_media() / "escenarios").glob("*")}


# --- adaptador de Gemini con transporte simulado ------------------------------------------


def _adaptador(manejador, clave: str = CLAVE) -> tuple[AdaptadorGemini, list[httpx.Request]]:
    vistas: list[httpx.Request] = []

    def envoltorio(peticion: httpx.Request) -> httpx.Response:
        vistas.append(peticion)
        return manejador(peticion)

    cliente = httpx.Client(transport=httpx.MockTransport(envoltorio))
    return AdaptadorGemini(clave, "modelo-de-prueba", 5, cliente=cliente), vistas


def _respuesta_con_imagen(contenido: bytes = PNG) -> httpx.Response:
    parte = {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(contenido).decode()}}
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": "ok"}, parte]}}]}
    )


def test_el_adaptador_manda_la_clave_en_el_encabezado_y_no_en_la_url() -> None:
    adaptador, vistas = _adaptador(lambda p: _respuesta_con_imagen())

    imagen = adaptador.generar("Un aula", 1536, 1024)

    assert imagen == PNG
    peticion = vistas[0]
    assert peticion.headers["x-goog-api-key"] == CLAVE
    assert CLAVE not in str(peticion.url) and "key=" not in str(peticion.url)
    assert str(peticion.url).endswith("/models/modelo-de-prueba:generateContent")
    cuerpo = json.loads(peticion.content)
    assert cuerpo["contents"][0]["parts"][0]["text"] == "Un aula"
    assert cuerpo["generationConfig"]["responseModalities"] == ["IMAGE"]
    assert CLAVE not in repr(adaptador)


@pytest.mark.parametrize(
    ("ancho", "alto", "relacion"),
    [(1024, 1024, "1:1"), (1536, 1024, "3:2"), (1024, 1536, "2:3")],
)
def test_cada_tamano_se_traduce_a_su_relacion_de_aspecto(ancho, alto, relacion) -> None:
    adaptador, vistas = _adaptador(lambda p: _respuesta_con_imagen())

    adaptador.generar("x", ancho, alto)

    cuerpo = json.loads(vistas[0].content)
    assert cuerpo["generationConfig"]["imageConfig"]["aspectRatio"] == relacion


def test_el_adaptador_rechaza_tamanos_libres_sin_llamar_al_proveedor() -> None:
    adaptador, vistas = _adaptador(lambda p: _respuesta_con_imagen())
    with pytest.raises(ValueError):
        adaptador.generar("x", 800, 600)
    assert vistas == []


def test_proveedor_429_se_traduce_a_saturado() -> None:
    adaptador, _ = _adaptador(
        lambda p: httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
    )
    with pytest.raises(ErrorLimiteExcedido) as error:
        adaptador.generar("x", 1024, 1024)
    assert error.value.estado_http == 429
    assert error.value.codigo == "PROVEEDOR_IMAGENES_SATURADO"
    assert "saturado" in error.value.mensaje


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(
            400,
            json={
                "error": {"status": "INVALID_ARGUMENT", "message": "Prompt blocked due to SAFETY"}
            },
        ),
        httpx.Response(200, json={"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}}),
        httpx.Response(200, json={"candidates": [{"finishReason": "IMAGE_SAFETY"}]}),
    ],
)
def test_contenido_bloqueado_se_traduce_a_prompt_rechazado(respuesta) -> None:
    adaptador, _ = _adaptador(lambda p: respuesta)
    with pytest.raises(ErrorValidacion) as error:
        adaptador.generar("x", 1024, 1024)
    assert error.value.estado_http == 422
    assert error.value.codigo == "PROMPT_RECHAZADO"
    assert "Reformúlala" in error.value.mensaje


def test_el_tiempo_agotado_se_traduce_a_504_con_mensaje_para_reintentar() -> None:
    def tarda(peticion):
        raise httpx.ReadTimeout("se agotó", request=peticion)

    adaptador, _ = _adaptador(tarda)
    with pytest.raises(ErrorTiempoAgotado) as error:
        adaptador.generar("x", 1024, 1024)
    assert error.value.estado_http == 504
    assert "tardó demasiado" in error.value.mensaje and "Inténtalo de nuevo" in error.value.mensaje


@pytest.mark.parametrize(
    ("respuesta", "codigo"),
    [
        (
            httpx.Response(400, json={"error": {"message": "argumento inválido"}}),
            "PROVEEDOR_IMAGENES_ERROR",
        ),
        (httpx.Response(500, text="boom"), "PROVEEDOR_IMAGENES_ERROR"),
        (
            httpx.Response(401, json={"error": {"message": f"API key {CLAVE} not valid"}}),
            "PROVEEDOR_IMAGENES_CONFIGURACION",
        ),
        (
            httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}),
            "PROVEEDOR_IMAGENES_CONFIGURACION",
        ),
        (
            httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": "solo texto"}]}}]}
            ),
            "PROVEEDOR_IMAGENES_SIN_IMAGEN",
        ),
        (
            httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"inlineData": {"data": "###"}}]}}]},
            ),
            "PROVEEDOR_IMAGENES_RESPUESTA_INVALIDA",
        ),
    ],
)
def test_otros_errores_del_proveedor_dan_502_sin_filtrar_su_cuerpo(respuesta, codigo) -> None:
    adaptador, _ = _adaptador(lambda p: respuesta)
    with pytest.raises(ErrorProveedorExterno) as error:
        adaptador.generar("x", 1024, 1024)
    assert error.value.estado_http == 502 and error.value.codigo == codigo
    assert CLAVE not in error.value.mensaje


def test_un_fallo_de_red_no_filtra_la_url_ni_la_clave(caplog) -> None:
    def sin_red(peticion):
        raise httpx.ConnectError("no hay red", request=peticion)

    adaptador, _ = _adaptador(sin_red)
    with caplog.at_level(logging.DEBUG), pytest.raises(ErrorProveedorExterno) as error:
        adaptador.generar("x", 1024, 1024)
    assert error.value.codigo == "PROVEEDOR_IMAGENES_SIN_CONEXION"
    assert CLAVE not in caplog.text and "googleapis" not in error.value.mensaje


# --- configuración -----------------------------------------------------------------------


def test_la_configuracion_arranca_sin_clave_y_trae_valores_por_defecto(monkeypatch) -> None:
    for variable in (
        "GEMINI_API_KEY",
        "GEMINI_MODELO_IMAGEN",
        "GEMINI_TIMEOUT_SEG",
        "GENERACION_IMAGENES_ACTIVA",
        "GENERACION_MAX_POR_HORA",
    ):
        monkeypatch.delenv(variable, raising=False)

    configuracion = Configuracion(_env_file=None)

    assert configuracion.gemini_api_key.get_secret_value() == ""
    assert configuracion.gemini_timeout_seg == 60
    assert configuracion.generacion_imagenes_activa is True
    assert configuracion.generacion_max_por_hora == 10
    assert configuracion.gemini_modelo_imagen
    assert "configurad" in motivo_no_disponible(configuracion)


def test_la_clave_no_sale_en_repr_ni_en_str_de_la_configuracion() -> None:
    configuracion = obtener_configuracion()
    assert CLAVE not in repr(configuracion) and CLAVE not in str(configuracion)
    assert CLAVE not in configuracion.model_dump_json()


# --- endpoint: camino feliz ---------------------------------------------------------------


def test_generar_guarda_el_archivo_con_su_origen_y_su_prompt(
    cliente, db, taller, generador
) -> None:
    respuesta = _generar(cliente, taller, "  Un pasillo vacío  ", tamano="1024x1536")

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["origen"] == "GENERADO_IA" and cuerpo["prompt_generacion"] == "Un pasillo vacío"
    assert cuerpo["tipo_mime"] == "image/png" and cuerpo["url"].startswith("/media/escenarios/")
    assert generador.llamadas == [("Un pasillo vacío", 1024, 1536)]
    assert cliente.get(cuerpo["url"]).content == PNG
    galeria = cliente.get("/api/v1/archivos", headers=taller["cabeceras"]).json()
    assert [(a["id"], a["origen"], a["prompt_generacion"]) for a in galeria] == [
        (cuerpo["id"], "GENERADO_IA", "Un pasillo vacío")
    ]
    assert _filas(db, taller["docente_id"]) == 1


def test_la_imagen_subida_a_mano_sigue_siendo_subida_y_sin_prompt(cliente, taller) -> None:
    subida = _subir(cliente, taller["cabeceras"]).json()
    assert subida["origen"] == "SUBIDO" and subida["prompt_generacion"] is None


def test_la_imagen_generada_se_puede_usar_como_capa_de_la_composicion(
    cliente, taller, generador
) -> None:
    archivo = _generar(cliente, taller).json()
    composicion = _composicion(archivo["id"])
    composicion["capas"][1]["origen"] = "IA"

    guardada = cliente.put(
        f"/api/v1/cases/{taller['caso_id']}/escenarios/{taller['escenarios'][0]}/composicion",
        headers=taller["cabeceras"],
        json=composicion,
    )

    assert guardada.status_code == 200, guardada.text
    assert guardada.json()["capas"][0]["origen"] == "IA"
    assert guardada.json()["capas"][0]["url"] == archivo["url"]


def test_el_estado_dice_cuantas_quedan_y_ofrece_tres_tamanos(cliente, taller, generador) -> None:
    _generar(cliente, taller)

    estado = cliente.get("/api/v1/archivos/generacion", headers=taller["cabeceras"]).json()

    assert estado["disponible"] is True and estado["motivo"] is None
    assert estado["restantes"] == estado["max_por_hora"] - 1
    assert [t["valor"] for t in estado["tamanos"]] == ["1024x1024", "1536x1024", "1024x1536"]
    assert CLAVE not in json.dumps(estado)


# --- endpoint: disponibilidad -------------------------------------------------------------


@pytest.mark.parametrize("clave", ["", "   ", "CAMBIAR-EN-PRODUCCION"])
def test_sin_clave_responde_503_claro_y_no_llama_al_generador(
    cliente, taller, generador, monkeypatch, clave
) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(obtener_configuracion(), "gemini_api_key", SecretStr(clave))

    respuesta = _generar(cliente, taller)

    assert respuesta.status_code == 503
    assert respuesta.json()["error"]["codigo"] == "GENERACION_NO_DISPONIBLE"
    assert "no está configurada" in respuesta.json()["error"]["mensaje"]
    assert generador.llamadas == []
    estado = cliente.get("/api/v1/archivos/generacion", headers=taller["cabeceras"]).json()
    assert estado["disponible"] is False and estado["motivo"]


def test_desactivada_responde_503_claro(cliente, taller, generador, monkeypatch) -> None:
    monkeypatch.setattr(obtener_configuracion(), "generacion_imagenes_activa", False)

    respuesta = _generar(cliente, taller)

    assert respuesta.status_code == 503
    assert "desactivada" in respuesta.json()["error"]["mensaje"]
    assert generador.llamadas == []


def test_sin_clave_la_app_responde_igual_en_lo_demas(cliente, taller, monkeypatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(obtener_configuracion(), "gemini_api_key", SecretStr(""))
    assert cliente.get("/health").status_code == 200
    assert _subir(cliente, taller["cabeceras"]).status_code == 201


def test_el_503_no_se_adelanta_a_los_permisos(cliente, taller, generador, monkeypatch) -> None:
    monkeypatch.setattr(obtener_configuracion(), "generacion_imagenes_activa", False)
    cuerpo = {"caso_id": taller["caso_id"], "escenario_id": taller["escenarios"][0], "prompt": "x"}

    sin_sesion = cliente.post(RUTA_GENERAR, json=cuerpo)
    ajeno = cliente.post(RUTA_GENERAR, headers=taller["otro"], json=cuerpo)

    assert sin_sesion.status_code == 401 and ajeno.status_code == 403


# --- endpoint: validación y permisos ------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": "a" * 501},
        {"tamano": "800x600"},
        {"tamano": "2048x2048"},
        {"modelo": "otro"},
    ],
)
def test_el_endpoint_valida_prompt_tamano_y_campos_extra(cliente, taller, generador, extra) -> None:
    cuerpo = {
        "caso_id": taller["caso_id"],
        "escenario_id": taller["escenarios"][0],
        "prompt": "ok",
        **extra,
    }

    respuesta = cliente.post(RUTA_GENERAR, headers=taller["cabeceras"], json=cuerpo)

    assert respuesta.status_code == 422 and generador.llamadas == []


def test_un_prompt_de_exactamente_500_caracteres_se_acepta(cliente, taller, generador) -> None:
    assert _generar(cliente, taller, "a" * 500).status_code == 201


def test_solo_el_docente_dueno_del_caso_en_borrador_genera(cliente, db, taller, generador) -> None:
    estudiante = cliente.post(
        RUTA_GENERAR,
        headers=_cabeceras(str(uuid.uuid4()), "ESTUDIANTE", permisos=()),
        json={"caso_id": taller["caso_id"], "escenario_id": taller["escenarios"][0], "prompt": "x"},
    )
    ajeno = _generar(cliente, taller, cabeceras=taller["otro"])
    escenario_de_otro_caso = cliente.post(
        RUTA_GENERAR,
        headers=taller["cabeceras"],
        json={"caso_id": taller["caso_id"], "escenario_id": str(uuid.uuid4()), "prompt": "x"},
    )
    db.execute(
        text("UPDATE caso SET estado = 'PUBLICADO' WHERE id = :id"), {"id": taller["caso_id"]}
    )
    db.commit()
    publicado = _generar(cliente, taller)

    assert estudiante.status_code == 401
    assert ajeno.status_code == 403
    assert escenario_de_otro_caso.status_code == 404
    assert publicado.status_code == 409
    assert generador.llamadas == []


# --- tope por hora ------------------------------------------------------------------------


def test_el_tope_por_hora_responde_429_con_la_hora_de_retorno(
    cliente, taller, generador, monkeypatch
) -> None:
    monkeypatch.setattr(obtener_configuracion(), "generacion_max_por_hora", 2)

    primeras = [_generar(cliente, taller).status_code for _ in range(2)]
    tercera = _generar(cliente, taller)
    otro_docente = cliente.get("/api/v1/archivos/generacion", headers=taller["otro"]).json()

    assert primeras == [201, 201]
    assert tercera.status_code == 429
    error = tercera.json()["error"]
    assert error["codigo"] == "LIMITE_GENERACION_ALCANZADO"
    assert "2 imágenes" in error["mensaje"] and "hora de Bogotá" in error["mensaje"]
    assert error["detalles"]["max_por_hora"] == 2
    assert len(generador.llamadas) == 2
    assert (
        cliente.get("/api/v1/archivos/generacion", headers=taller["cabeceras"]).json()["restantes"]
        == 0
    )
    assert otro_docente["restantes"] == 2  # el tope es por docente


class RelojMutable:
    def __init__(self, instante: datetime) -> None:
        self.instante = instante

    def ahora(self) -> datetime:
        return self.instante


def test_el_tope_se_reinicia_cada_hora_de_reloj_con_reloj_falso(
    db, taller, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(obtener_configuracion(), "generacion_max_por_hora", 2)
    reloj = RelojMutable(datetime(2026, 11, 25, 10, 50, tzinfo=UTC))
    falso = GeneradorFalso()
    servicio = ServicioArchivos(
        db,
        almacenamiento=AlmacenamientoLocal(tmp_path),
        reloj=reloj,
        autorizar_escenario=lambda *_: None,
        fabrica_generador=lambda: falso,
    )
    sesion = {"sub": taller["docente_id"], "rol": "DOCENTE"}

    def pedir():
        return servicio.generar_imagen(
            sesion, taller["caso_id"], taller["escenarios"][0], "x", "1024x1024"
        )

    pedir()
    reloj.instante = datetime(2026, 11, 25, 10, 59, 59, tzinfo=UTC)
    pedir()
    with pytest.raises(ErrorLimiteExcedido) as error:
        pedir()
    assert "06:00" in error.value.mensaje  # 11:00 UTC = 06:00 en Bogotá
    assert error.value.detalles["reintentar_a"].startswith("2026-11-25T11:00:00")

    reloj.instante = datetime(2026, 11, 25, 11, 0, 0, tzinfo=UTC)
    pedir()  # nueva hora de reloj: el contador vuelve a cero
    assert len(falso.llamadas) == 3
    reloj.instante += timedelta(hours=1)
    assert servicio.estado_generacion(sesion)["restantes"] == 2


def test_dos_generaciones_a_la_vez_del_mismo_docente_dan_409(cliente, taller, generador) -> None:
    _generando.add(taller["docente_id"])
    try:
        respuesta = _generar(cliente, taller)
    finally:
        _generando.discard(taller["docente_id"])

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["codigo"] == "GENERACION_EN_CURSO"
    assert generador.llamadas == []
    assert _generar(cliente, taller).status_code == 201  # el candado se libera


# --- errores del proveedor a través del endpoint ------------------------------------------


@pytest.mark.parametrize(
    ("error", "estado", "codigo"),
    [
        (
            ErrorLimiteExcedido("saturado", codigo="PROVEEDOR_IMAGENES_SATURADO"),
            429,
            "PROVEEDOR_IMAGENES_SATURADO",
        ),
        (ErrorValidacion("rechazado", codigo="PROMPT_RECHAZADO"), 422, "PROMPT_RECHAZADO"),
        (
            ErrorTiempoAgotado("tardó demasiado", codigo="GENERACION_TIEMPO_AGOTADO"),
            504,
            "GENERACION_TIEMPO_AGOTADO",
        ),
        (ErrorProveedorExterno("falló"), 502, "PROVEEDOR_EXTERNO_FALLIDO"),
    ],
)
def test_un_error_del_proveedor_no_deja_archivo_ni_fila(
    cliente, db, taller, generador, error, estado, codigo
) -> None:
    generador.error = error
    antes = _archivos_en_disco()

    respuesta = _generar(cliente, taller)

    assert (respuesta.status_code, respuesta.json()["error"]["codigo"]) == (estado, codigo)
    assert _filas(db, taller["docente_id"]) == 0
    assert _archivos_en_disco() == antes
    generador.error = None
    assert _generar(cliente, taller).status_code == 201  # falló sin gastar el cupo ni el candado


def test_una_respuesta_que_no_es_jpg_ni_png_da_502_sin_dejar_nada(
    cliente, db, taller, generador
) -> None:
    generador.contenido = b"RIFF....WEBPVP8 "
    antes = _archivos_en_disco()

    respuesta = _generar(cliente, taller)

    assert respuesta.status_code == 502
    assert respuesta.json()["error"]["codigo"] == "PROVEEDOR_IMAGENES_RESPUESTA_INVALIDA"
    assert _filas(db, taller["docente_id"]) == 0 and _archivos_en_disco() == antes


def test_un_jpg_generado_tambien_se_acepta(cliente, taller, generador) -> None:
    generador.contenido = JPG
    assert _generar(cliente, taller).json()["tipo_mime"] == "image/jpeg"


# --- atomicidad ---------------------------------------------------------------------------


def _servicio(db, almacenamiento, falso=None):
    return ServicioArchivos(
        db,
        almacenamiento=almacenamiento,
        autorizar_escenario=lambda *_: None,
        fabrica_generador=lambda: falso or GeneradorFalso(),
    )


def test_si_el_guardado_falla_no_queda_fila_ni_archivo(db, taller, tmp_path) -> None:
    class AlmacenamientoRoto(AlmacenamientoLocal):
        def guardar(self, contenido, nombre, tipo_mime):
            raise OSError("disco lleno")

    servicio = _servicio(db, AlmacenamientoRoto(tmp_path))
    sesion = {"sub": taller["docente_id"], "rol": "DOCENTE"}

    from app.core.exceptions import ErrorAlmacenamiento

    with pytest.raises(ErrorAlmacenamiento):
        servicio.generar_imagen(
            sesion, taller["caso_id"], taller["escenarios"][0], "x", "1024x1024"
        )

    assert _filas(db, taller["docente_id"]) == 0
    assert list(tmp_path.rglob("*")) == []


def test_si_la_fila_falla_se_borra_el_archivo_ya_escrito(db, taller, tmp_path, monkeypatch) -> None:
    servicio = _servicio(db, AlmacenamientoLocal(tmp_path))
    sesion = {"sub": taller["docente_id"], "rol": "DOCENTE"}

    def commit_roto():
        raise RuntimeError("falló el commit")

    monkeypatch.setattr(db, "commit", commit_roto)
    with pytest.raises(RuntimeError):
        servicio.generar_imagen(
            sesion, taller["caso_id"], taller["escenarios"][0], "x", "1024x1024"
        )
    monkeypatch.undo()

    assert _filas(db, taller["docente_id"]) == 0
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


def test_la_escritura_en_disco_no_deja_parciales_si_se_interrumpe(tmp_path, monkeypatch) -> None:
    import app.core.almacenamiento as modulo

    def falla(origen, destino):
        raise OSError("interrumpido")

    monkeypatch.setattr(modulo.os, "replace", falla)
    with pytest.raises(OSError):
        AlmacenamientoLocal(tmp_path).guardar(PNG, "escenarios/a.png", "image/png")
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == []


# --- la clave no se filtra ----------------------------------------------------------------


def test_la_clave_no_aparece_en_respuestas_ni_en_logs_cuando_el_proveedor_falla(
    cliente, taller, caplog
) -> None:
    def rechaza(peticion):
        return httpx.Response(
            401,
            json={"error": {"message": f"API key {CLAVE} not valid", "status": "UNAUTHENTICATED"}},
        )

    adaptador, _ = _adaptador(rechaza)
    app.dependency_overrides[obtener_fabrica_generador] = lambda: lambda: adaptador
    try:
        with caplog.at_level(logging.DEBUG):
            fallida = _generar(cliente, taller)
            estado = cliente.get("/api/v1/archivos/generacion", headers=taller["cabeceras"])
    finally:
        app.dependency_overrides.pop(obtener_fabrica_generador, None)

    assert fallida.status_code == 502
    assert fallida.json()["error"]["codigo"] == "PROVEEDOR_IMAGENES_CONFIGURACION"
    assert CLAVE not in fallida.text and CLAVE not in estado.text and CLAVE not in caplog.text


# --- migración ----------------------------------------------------------------------------


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


def _columnas() -> set[str]:
    with SessionLocal() as sesion:
        filas = sesion.execute(
            text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'archivo_adjunto'"
            )
        ).all()
    return {fila[0] for fila in filas}


def test_la_migracion_de_origen_conserva_los_archivos_existentes_como_subidos(
    base_real, taller
) -> None:
    ruta = f"escenarios/{uuid.uuid4()}.png"
    try:
        _alembic("downgrade", "0014_composiciones")
        assert {"origen", "prompt_generacion"}.isdisjoint(_columnas())
        with SessionLocal() as sesion:
            sesion.execute(
                text(
                    "INSERT INTO archivo_adjunto (id, docente_id, nombre_original, tipo_mime, "
                    "tamano_bytes, ruta_almacenamiento, creado_en) "
                    "VALUES (:id, :docente, 'viejo.png', 'image/png', 10, :ruta, UTC_TIMESTAMP(6))"
                ),
                {"id": str(uuid.uuid4()), "docente": taller["docente_id"], "ruta": ruta},
            )
            sesion.commit()
    finally:
        _alembic("upgrade", "head")

    assert {"origen", "prompt_generacion"} <= _columnas()
    with SessionLocal() as sesion:
        fila = sesion.execute(
            text(
                "SELECT origen, prompt_generacion FROM archivo_adjunto "
                "WHERE ruta_almacenamiento = :r"
            ),
            {"r": ruta},
        ).one()
        assert tuple(fila) == ("SUBIDO", None)
        with pytest.raises(Exception, match="origen|constraint|CONSTRAINT"):
            sesion.execute(
                text(
                    "UPDATE archivo_adjunto SET origen = 'INVENTADO' WHERE ruta_almacenamiento = :r"
                ),
                {"r": ruta},
            )
        sesion.rollback()
        sesion.execute(delete(ArchivoAdjunto).where(ArchivoAdjunto.ruta_almacenamiento == ruta))
        sesion.commit()
