"""Puzzles lógicos (Fase 13): contenido, vista sin solución, verificación y que NO puntúan."""

import os
import subprocess
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, text

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.exceptions import ErrorValidacion
from app.core.security import crear_jwt, descifrar
from app.modules.auth.models import Usuario
from app.modules.cases.models import (
    Caso,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Puzzle,
    Rubrica,
)
from app.modules.cases.puzzles import (
    CLASIFICAR,
    EMPAREJAR_CONCEPTOS,
    ORDENAR_SECUENCIA,
    PIEZA_FALTANTE,
    validar_contenido,
    verificar,
    vista_estudiante,
)
from app.modules.notifications.models import EventoOutbox
from app.modules.sessions.models import EspacioAcademico, Sesion
from app.modules.sessions.schemas import ConvocadoEntrada
from app.modules.sessions.service import ServicioSesiones

RAIZ = Path(__file__).resolve().parent.parent

CONTENIDO_ORDENAR = {"tiempo_seg": 40, "pasos": ["Observar", "Escuchar", "Calmar", "Conectar"]}
CONTENIDO_EMPAREJAR = {
    "pares": [
        {"termino": "Ley 1257", "definicion": "Violencias contra la mujer"},
        {"termino": "Ley 2126", "definicion": "Comisarías de Familia"},
        {"termino": "Ley 1098", "definicion": "Infancia y adolescencia"},
    ]
}
CONTENIDO_PIEZA = {
    "serie": ["Detectar", "Valorar", "Proteger", "Remitir"],
    "faltante": 2,
    "distractores": ["Archivar", "Esperar"],
}
CONTENIDO_CLASIFICAR = {
    "categorias": ["Salud", "Comisaría"],
    "elementos": [
        {"texto": "Primeros auxilios", "categoria": "Salud"},
        {"texto": "Valoración clínica", "categoria": "Salud"},
        {"texto": "Medidas de protección", "categoria": "Comisaría"},
    ],
}
RESPUESTA_CORRECTA = {
    ORDENAR_SECUENCIA: {"orden": ["Observar", "Escuchar", "Calmar", "Conectar"]},
    EMPAREJAR_CONCEPTOS: {"pares": CONTENIDO_EMPAREJAR["pares"]},
    PIEZA_FALTANTE: {"opcion": "Proteger"},
    CLASIFICAR: {"asignaciones": CONTENIDO_CLASIFICAR["elementos"]},
}
RESPUESTA_INCORRECTA = {
    ORDENAR_SECUENCIA: {"orden": ["Conectar", "Calmar", "Escuchar", "Observar"]},
    EMPAREJAR_CONCEPTOS: {
        "pares": [
            {"termino": "Ley 1257", "definicion": "Comisarías de Familia"},
            {"termino": "Ley 2126", "definicion": "Violencias contra la mujer"},
            {"termino": "Ley 1098", "definicion": "Infancia y adolescencia"},
        ]
    },
    PIEZA_FALTANTE: {"opcion": "Archivar"},
    CLASIFICAR: {
        "asignaciones": [
            {"texto": "Primeros auxilios", "categoria": "Comisaría"},
            {"texto": "Valoración clínica", "categoria": "Salud"},
            {"texto": "Medidas de protección", "categoria": "Comisaría"},
        ]
    },
}
CONTENIDOS = {
    ORDENAR_SECUENCIA: CONTENIDO_ORDENAR,
    EMPAREJAR_CONCEPTOS: CONTENIDO_EMPAREJAR,
    PIEZA_FALTANTE: CONTENIDO_PIEZA,
    CLASIFICAR: CONTENIDO_CLASIFICAR,
}


# --- unidad: contenido, vista del estudiante y verificación ------------------------------


@pytest.mark.parametrize("tipo", list(CONTENIDOS))
def test_el_contenido_valido_se_normaliza_con_tiempo_por_defecto(tipo) -> None:
    contenido = validar_contenido(tipo, CONTENIDOS[tipo])

    assert 30 <= contenido["tiempo_seg"] <= 60


@pytest.mark.parametrize(
    ("tipo", "contenido", "fragmento"),
    [
        (ORDENAR_SECUENCIA, {"pasos": ["A", "B"]}, "pasos"),
        (ORDENAR_SECUENCIA, {"pasos": ["A", "a", "C"]}, "repetirse"),
        (ORDENAR_SECUENCIA, {**CONTENIDO_ORDENAR, "tiempo_seg": 20}, "tiempo_seg"),
        (ORDENAR_SECUENCIA, {**CONTENIDO_ORDENAR, "extra": 1}, "extra"),
        (
            EMPAREJAR_CONCEPTOS,
            {"pares": [{"termino": f"T{i}", "definicion": "igual"} for i in range(3)]},
            "definiciones",
        ),
        (PIEZA_FALTANTE, {**CONTENIDO_PIEZA, "faltante": 9}, "faltante"),
        (PIEZA_FALTANTE, {**CONTENIDO_PIEZA, "distractores": ["Proteger"]}, "opciones"),
        (
            CLASIFICAR,
            {**CONTENIDO_CLASIFICAR, "categorias": ["Salud", "Comisaría", "Vacía"]},
            "al menos un elemento",
        ),
        (
            CLASIFICAR,
            {
                "categorias": ["Salud", "Comisaría"],
                "elementos": [{"texto": f"E{i}", "categoria": "Otra"} for i in range(3)],
            },
            "categorías",
        ),
    ],
)
def test_el_contenido_invalido_se_rechaza_con_un_mensaje_claro(tipo, contenido, fragmento) -> None:
    with pytest.raises(ErrorValidacion) as error:
        validar_contenido(tipo, contenido)

    assert fragmento in (error.value.mensaje + str(error.value.detalles))


def test_un_tipo_desconocido_se_rechaza() -> None:
    with pytest.raises(ErrorValidacion):
        validar_contenido("ADIVINAR", {})


@pytest.mark.parametrize("tipo", list(CONTENIDOS))
def test_la_vista_del_estudiante_no_contiene_la_solucion(tipo) -> None:
    contenido = validar_contenido(tipo, CONTENIDOS[tipo])

    tiempo, datos = vista_estudiante(tipo, contenido)
    texto = str(datos)

    assert tiempo == contenido["tiempo_seg"]
    for clave_de_solucion in ("pasos", "pares", "faltante", "distractores", "'categoria'"):
        assert clave_de_solucion not in texto


def test_ordenar_se_entrega_barajado_nunca_en_el_orden_correcto() -> None:
    contenido = validar_contenido(ORDENAR_SECUENCIA, CONTENIDO_ORDENAR)

    for _ in range(40):
        _, datos = vista_estudiante(ORDENAR_SECUENCIA, contenido)
        assert datos["elementos"] != contenido["pasos"]
        assert sorted(datos["elementos"]) == sorted(contenido["pasos"])


def test_pieza_faltante_oculta_la_pieza_y_ofrece_la_correcta_entre_las_opciones() -> None:
    contenido = validar_contenido(PIEZA_FALTANTE, CONTENIDO_PIEZA)

    _, datos = vista_estudiante(PIEZA_FALTANTE, contenido)

    assert datos["serie"][2] is None
    assert datos["serie"][:2] == ["Detectar", "Valorar"]
    assert sorted(datos["opciones"]) == ["Archivar", "Esperar", "Proteger"]


@pytest.mark.parametrize("tipo", list(CONTENIDOS))
def test_verificar_distingue_la_respuesta_correcta_de_la_incorrecta(tipo) -> None:
    contenido = validar_contenido(tipo, CONTENIDOS[tipo])

    assert verificar(tipo, contenido, RESPUESTA_CORRECTA[tipo]) is True
    assert verificar(tipo, contenido, RESPUESTA_INCORRECTA[tipo]) is False


def test_verificar_ignora_mayusculas_y_espacios_y_rechaza_respuestas_incompletas() -> None:
    contenido = validar_contenido(ORDENAR_SECUENCIA, CONTENIDO_ORDENAR)

    assert verificar(
        ORDENAR_SECUENCIA, contenido, {"orden": [" observar", "ESCUCHAR ", "calmar", "Conectar"]}
    )
    assert not verificar(ORDENAR_SECUENCIA, contenido, {"orden": ["Observar", "Escuchar"]})
    contenido = validar_contenido(EMPAREJAR_CONCEPTOS, CONTENIDO_EMPAREJAR)
    assert not verificar(
        EMPAREJAR_CONCEPTOS, contenido, {"pares": CONTENIDO_EMPAREJAR["pares"][:2]}
    )
    with pytest.raises(ErrorValidacion):
        verificar(ORDENAR_SECUENCIA, contenido, {"otra_cosa": 1})


# --- integración contra MySQL real -------------------------------------------------------


def _usuario(rol: str, nombre: str, sufijo: str) -> Usuario:
    momento = ahora()
    dominio = obtener_configuracion().dominio_principal
    return Usuario(
        nombre=nombre,
        correo=f"{nombre.lower()}.{sufijo}@{dominio}",
        rol=rol,
        activo=True,
        correo_verificado=True,
        creado_en=momento,
        actualizado_en=momento,
    )


def _puzzle(escenario, orden, tipo, enunciado) -> Puzzle:
    return Puzzle(
        escenario=escenario,
        orden=orden,
        tipo=tipo,
        enunciado=enunciado,
        contenido=validar_contenido(tipo, CONTENIDOS[tipo]),
        creado_en=ahora(),
    )


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def juego(db):
    """Caso publicado de 2 escenarios con los 4 tipos de puzzle y dos estudiantes convocados."""
    momento = ahora()
    sufijo = uuid.uuid4().hex[:8]
    docente = _usuario("DOCENTE", "Docente", sufijo)
    db.add(docente)
    db.flush()

    caso = Caso(
        docente_creador_id=docente.id,
        nombre="Caso con puzzles",
        desarrollo_situacional="Desarrollo",
        contexto_historia="Historia",
        tiempo_estimado_min=30,
        estado="PUBLICADO",
        version=1,
        creado_en=momento,
        actualizado_en=momento,
    )
    esc1 = Escenario(caso=caso, orden=1, titulo="Capítulo 1", contexto="Contexto 1")
    esc2 = Escenario(caso=caso, orden=2, titulo="Capítulo 2", contexto="Contexto 2")
    preguntas = []
    for escenario, numero in ((esc1, 1), (esc1, 2), (esc2, 1)):
        pregunta = Pregunta(escenario=escenario, orden=numero, enunciado=f"Pregunta {numero}")
        pregunta.opciones = [
            Opcion(
                pregunta=pregunta, orden=1, texto="Correcta", es_correcta=True, justificacion="Sí"
            ),
            Opcion(pregunta=pregunta, orden=2, texto="Mala", es_correcta=False, justificacion="No"),
        ]
        preguntas.append(pregunta)
    puzzles = [
        _puzzle(esc1, 1, ORDENAR_SECUENCIA, "Ordena los pasos"),
        _puzzle(esc1, 2, EMPAREJAR_CONCEPTOS, "Une cada ley"),
        _puzzle(esc1, 3, PIEZA_FALTANTE, "Completa la ruta"),
        _puzzle(esc2, 1, CLASIFICAR, "Clasifica las acciones"),
    ]
    rubrica = Rubrica(
        caso=caso,
        nombre="Rúbrica",
        escala_min=Decimal("0.00"),
        escala_max=Decimal("5.00"),
        nota_aprobatoria=Decimal("3.00"),
        publicada=True,
        creada_en=momento,
        actualizada_en=momento,
    )
    CriterioRubrica(
        rubrica=rubrica, orden=1, nombre="Único", peso=Decimal("100.00")
    ).preguntas = preguntas
    espacio = EspacioAcademico(nombre=f"Espacio {sufijo}", docente_id=docente.id, creado_en=momento)
    db.add_all([caso, espacio])
    db.flush()
    sesion = Sesion(
        caso_id=caso.id,
        docente_id=docente.id,
        espacio_academico_id=espacio.id,
        inicio_programado=momento,
        fin_programado=momento + timedelta(hours=2),
        tiempo_maximo_min=30,
        estado="EN_CURSO",
        iniciada_en=momento,
        creada_en=momento,
    )
    db.add(sesion)
    db.commit()

    estudiantes = []
    for nombre in ("Ana", "Beto"):
        correo = f"{nombre.lower()}.{sufijo}@{obtener_configuracion().dominio_principal}"
        convocatoria = ServicioSesiones(db).agregar_convocado(
            sesion,
            ConvocadoEntrada(correo=correo, nombre=nombre),
            {"rol": "DOCENTE", "sub": docente.id},
        )
        estudiantes.append(
            {
                "correo": correo,
                "codigo": descifrar(convocatoria.codigo_cifrado),
                "convocatoria_id": convocatoria.id,
            }
        )
    db.rollback()
    puzzle_por_tipo = {p.tipo: p.id for p in puzzles}
    datos = {
        "docente_id": docente.id,
        "caso_id": caso.id,
        "estudiantes": estudiantes,
        "puzzles": puzzle_por_tipo,
        "preguntas": [
            {
                "id": p.id,
                "correcta": next(o.id for o in p.opciones if o.es_correcta),
                "mala": next(o.id for o in p.opciones if not o.es_correcta),
            }
            for p in preguntas
        ],
    }
    yield datos

    db.rollback()
    db.execute(delete(Caso).where(Caso.caso_origen_id == caso.id))
    db.execute(delete(EventoOutbox).where(EventoOutbox.creado_en >= momento))
    db.execute(delete(Sesion).where(Sesion.id == sesion.id))
    db.execute(delete(EspacioAcademico).where(EspacioAcademico.id == espacio.id))
    db.execute(delete(Caso).where(Caso.id == caso.id))
    db.execute(delete(Usuario).where(Usuario.correo.like(f"%.{sufijo}@%")))
    db.commit()


def _cabeceras_docente(docente_id: str, **extra) -> dict:
    token = crear_jwt(
        {
            "sub": docente_id,
            "rol": "DOCENTE",
            "permisos": ["CREAR_CASOS"],
            "estado_cuenta": "ACTIVO",
            **extra,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _cabeceras_estudiante(cliente, estudiante) -> dict:
    respuesta = cliente.post(
        "/api/v1/auth/student-login",
        json={"correo": estudiante["correo"], "codigo": estudiante["codigo"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['token_acceso']}"}


def _verificar(cliente, cabeceras, puzzle_id, respuesta):
    return cliente.post(
        f"/api/v1/puzzles/{puzzle_id}/verificar", headers=cabeceras, json={"respuesta": respuesta}
    )


def test_el_endpoint_del_estudiante_nunca_devuelve_la_solucion(cliente, juego) -> None:
    respuesta = cliente.get(f"/api/v1/cases/{juego['caso_id']}/vista-estudiante")

    assert respuesta.status_code == 200
    escenarios = respuesta.json()["escenarios"]
    puzzles = {p["tipo"]: p for e in escenarios for p in e["puzzles"]}
    assert set(puzzles) == set(CONTENIDOS)
    for p in puzzles.values():
        assert set(p) == {"id", "orden", "tipo", "enunciado", "tiempo_seg", "datos"}
    assert set(puzzles[ORDENAR_SECUENCIA]["datos"]) == {"elementos"}
    assert puzzles[ORDENAR_SECUENCIA]["datos"]["elementos"] != CONTENIDO_ORDENAR["pasos"]
    assert set(puzzles[EMPAREJAR_CONCEPTOS]["datos"]) == {"terminos", "definiciones"}
    assert puzzles[PIEZA_FALTANTE]["datos"]["serie"][2] is None
    assert set(puzzles[CLASIFICAR]["datos"]) == {"categorias", "elementos"}
    assert all(isinstance(e, str) for e in puzzles[CLASIFICAR]["datos"]["elementos"])
    for prohibido in (
        '"pasos"',
        '"pares"',
        '"faltante"',
        '"distractores"',
        '"categoria"',
        "contenido",
    ):
        assert prohibido not in respuesta.text
    # RF-14: tampoco se cuela la corrección de las preguntas.
    assert "es_correcta" not in respuesta.text and "justificacion" not in respuesta.text


@pytest.mark.parametrize("tipo", list(CONTENIDOS))
def test_verificar_responde_solo_acerto_sin_revelar_la_solucion(cliente, juego, tipo) -> None:
    cabeceras = _cabeceras_estudiante(cliente, juego["estudiantes"][0])
    puzzle_id = juego["puzzles"][tipo]

    bien = _verificar(cliente, cabeceras, puzzle_id, RESPUESTA_CORRECTA[tipo])
    mal = _verificar(cliente, cabeceras, puzzle_id, RESPUESTA_INCORRECTA[tipo])

    assert bien.status_code == mal.status_code == 200
    assert bien.json() == {"acerto": True}
    assert mal.json() == {"acerto": False}


def test_verificar_exige_sesion_y_solo_deja_jugar_los_puzzles_del_propio_caso(
    cliente, juego
) -> None:
    puzzle_id = juego["puzzles"][PIEZA_FALTANTE]
    estudiante_ajeno = {
        "Authorization": "Bearer "
        + crear_jwt({"sub": _uuid(), "rol": "ESTUDIANTE", "caso_id": _uuid()})
    }
    suyo = _cabeceras_estudiante(cliente, juego["estudiantes"][0])

    assert _verificar(cliente, {}, puzzle_id, {"opcion": "Proteger"}).status_code == 401
    assert (
        _verificar(cliente, estudiante_ajeno, puzzle_id, {"opcion": "Proteger"}).status_code == 403
    )
    docente_ajeno = _cabeceras_docente(_uuid())
    assert _verificar(cliente, docente_ajeno, puzzle_id, {"opcion": "Proteger"}).status_code == 403
    dueno = _cabeceras_docente(juego["docente_id"])
    assert _verificar(cliente, dueno, puzzle_id, {"opcion": "Proteger"}).json() == {"acerto": True}
    assert _verificar(cliente, suyo, _uuid(), {"opcion": "x"}).status_code == 404
    assert _verificar(cliente, suyo, puzzle_id, {"otra": 1}).status_code == 422


def _uuid() -> str:
    return str(uuid.uuid4())


def _jugar(cliente, estudiante, preguntas, elecciones):
    cabeceras = _cabeceras_estudiante(cliente, estudiante)
    inicio = cliente.post(
        f"/api/v1/participations/start/{estudiante['convocatoria_id']}", headers=cabeceras
    )
    assert inicio.status_code == 200, inicio.text
    participacion_id = inicio.json()["id"]
    for pregunta, clave in zip(preguntas, elecciones, strict=True):
        respuesta = cliente.put(
            f"/api/v1/participations/{participacion_id}/answers/{pregunta['id']}",
            headers=cabeceras,
            json={"opcion_id": pregunta[clave]},
        )
        assert respuesta.status_code == 200, respuesta.text
    final = cliente.post(f"/api/v1/participations/{participacion_id}/finish", headers=cabeceras)
    assert final.status_code == 200, final.text
    resultado = cliente.get(f"/api/v1/participations/{participacion_id}/result", headers=cabeceras)
    assert resultado.status_code == 200, resultado.text
    return cabeceras, resultado.json()


def test_fallar_o_saltar_un_puzzle_no_impide_responder_ni_finalizar_y_no_cambia_la_nota(
    cliente, juego
) -> None:
    ana, beto = juego["estudiantes"]
    cabeceras_ana = _cabeceras_estudiante(cliente, ana)
    for tipo, puzzle_id in juego["puzzles"].items():
        assert _verificar(cliente, cabeceras_ana, puzzle_id, RESPUESTA_CORRECTA[tipo]).json()[
            "acerto"
        ]
    cabeceras_beto = _cabeceras_estudiante(cliente, beto)
    # Beto falla un puzzle y se salta (no verifica) todos los demás.
    _verificar(
        cliente,
        cabeceras_beto,
        juego["puzzles"][ORDENAR_SECUENCIA],
        RESPUESTA_INCORRECTA[ORDENAR_SECUENCIA],
    )

    elecciones = ["correcta", "mala", "correcta"]
    _, resultado_ana = _jugar(cliente, ana, juego["preguntas"], elecciones)
    _, resultado_beto = _jugar(cliente, beto, juego["preguntas"], elecciones)

    assert resultado_ana["nota_final"] == resultado_beto["nota_final"]
    assert Decimal(resultado_ana["nota_final"]) == Decimal("3.33")
    assert (resultado_ana["aciertos"], resultado_ana["total_preguntas"]) == (2, 3)


def test_new_version_copia_los_puzzles_con_su_contenido(cliente, juego) -> None:
    respuesta = cliente.post(
        f"/api/v1/cases/{juego['caso_id']}/new-version",
        headers=_cabeceras_docente(juego["docente_id"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    nuevo = respuesta.json()
    original = cliente.get(
        f"/api/v1/cases/{juego['caso_id']}", headers=_cabeceras_docente(juego["docente_id"])
    ).json()
    copiados = [p for e in nuevo["escenarios"] for p in e["puzzles"]]
    originales = [p for e in original["escenarios"] for p in e["puzzles"]]
    assert len(copiados) == len(originales) == 4
    assert {p["id"] for p in copiados}.isdisjoint({p["id"] for p in originales})
    assert [(p["orden"], p["tipo"], p["enunciado"], p["contenido"]) for p in copiados] == [
        (p["orden"], p["tipo"], p["enunciado"], p["contenido"]) for p in originales
    ]


def _crear_borrador(cliente, docente_id):
    cabeceras = _cabeceras_docente(docente_id)
    caso = cliente.post(
        "/api/v1/cases",
        headers=cabeceras,
        json={
            "nombre": "Borrador con puzzles",
            "desarrollo_situacional": "d",
            "contexto_historia": "c",
            "tiempo_estimado_min": 30,
        },
    )
    assert caso.status_code == 201, caso.text
    escenario = cliente.post(
        f"/api/v1/cases/{caso.json()['id']}/escenarios",
        headers=cabeceras,
        json={"titulo": "E1", "contexto": "x"},
    )
    assert escenario.status_code == 200, escenario.text
    return cabeceras, caso.json()["id"], escenario.json()["id"]


def test_el_docente_crea_edita_ordena_y_borra_puzzles_con_un_maximo_de_tres(
    cliente, db, juego
) -> None:
    cabeceras, caso_id, escenario_id = _crear_borrador(cliente, juego["docente_id"])
    ruta = f"/api/v1/cases/{caso_id}/escenarios/{escenario_id}/puzzles"
    try:
        creados = [
            cliente.post(
                ruta,
                headers=cabeceras,
                json={"tipo": tipo, "enunciado": f"Puzzle {tipo}", "contenido": CONTENIDOS[tipo]},
            )
            for tipo in (ORDENAR_SECUENCIA, EMPAREJAR_CONCEPTOS, CLASIFICAR)
        ]
        assert [c.status_code for c in creados] == [201, 201, 201]
        assert [c.json()["orden"] for c in creados] == [1, 2, 3]
        assert creados[0].json()["contenido"]["tiempo_seg"] == 40

        cuarto = cliente.post(
            ruta,
            headers=cabeceras,
            json={"tipo": PIEZA_FALTANTE, "enunciado": "Otro", "contenido": CONTENIDO_PIEZA},
        )
        invalido = cliente.post(
            ruta,
            headers=cabeceras,
            json={"tipo": ORDENAR_SECUENCIA, "enunciado": "x", "contenido": {"pasos": ["A"]}},
        )
        assert cuarto.status_code == 409
        assert invalido.status_code == 422
        assert "pasos" in invalido.json()["error"]["mensaje"] + str(invalido.json()["error"])

        ids = [c.json()["id"] for c in creados]
        edicion = cliente.put(
            f"/api/v1/cases/{caso_id}/puzzles/{ids[0]}",
            headers=cabeceras,
            json={
                "tipo": ORDENAR_SECUENCIA,
                "enunciado": "Editado",
                "contenido": {**CONTENIDO_ORDENAR, "tiempo_seg": 60},
            },
        )
        assert edicion.status_code == 200 and edicion.json()["contenido"]["tiempo_seg"] == 60

        orden = cliente.put(
            f"/api/v1/cases/{caso_id}/orden/puzzles",
            headers=cabeceras,
            json={"ids": [ids[2], ids[0], ids[1]]},
        )
        assert orden.status_code == 200, orden.text
        por_orden = cliente.get(f"/api/v1/cases/{caso_id}", headers=cabeceras).json()
        assert [p["id"] for p in por_orden["escenarios"][0]["puzzles"]] == [ids[2], ids[0], ids[1]]

        previa = cliente.get(
            f"/api/v1/cases/{caso_id}/puzzles/{ids[0]}/vista-previa", headers=cabeceras
        )
        assert previa.status_code == 200
        assert "pasos" not in previa.text and "contenido" not in previa.text

        borrado = cliente.delete(f"/api/v1/cases/{caso_id}/puzzles/{ids[2]}", headers=cabeceras)
        assert borrado.status_code == 204
        restantes = cliente.get(f"/api/v1/cases/{caso_id}", headers=cabeceras).json()
        assert [p["orden"] for p in restantes["escenarios"][0]["puzzles"]] == [1, 2]
    finally:
        db.rollback()
        db.execute(delete(Caso).where(Caso.id == caso_id))
        db.commit()


def test_un_caso_publicado_es_inmutable_tambien_para_los_puzzles(cliente, juego) -> None:
    cabeceras = _cabeceras_docente(juego["docente_id"])
    caso = cliente.get(f"/api/v1/cases/{juego['caso_id']}", headers=cabeceras).json()
    escenario_id = caso["escenarios"][0]["id"]

    respuesta = cliente.post(
        f"/api/v1/cases/{juego['caso_id']}/escenarios/{escenario_id}/puzzles",
        headers=cabeceras,
        json={"tipo": CLASIFICAR, "enunciado": "x", "contenido": CONTENIDO_CLASIFICAR},
    )

    assert respuesta.status_code == 409


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


def _hay_tabla_puzzle() -> bool:
    with SessionLocal() as sesion:
        return bool(
            sesion.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'puzzle'"
                )
            ).scalar()
        )


def test_la_migracion_de_puzzles_baja_a_0012_y_vuelve_a_subir(base_real) -> None:
    assert _hay_tabla_puzzle()
    try:
        _alembic("downgrade", "0012_triggers_vistas")
        assert not _hay_tabla_puzzle()
    finally:
        _alembic("upgrade", "head")
    assert _hay_tabla_puzzle()
