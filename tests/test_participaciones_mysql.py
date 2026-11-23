"""Flujo del estudiante contra MySQL real: iniciar, responder, finalizar y ver el resultado.

MySQL devuelve los DATETIME sin zona horaria, así que estas pruebas cubren las comparaciones
entre fechas guardadas (naive) y el reloj UTC (aware) que las pruebas unitarias no ven.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.security import descifrar
from app.modules.auth.models import Usuario
from app.modules.cases.models import (
    Caso,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Rubrica,
)
from app.modules.notifications.models import EventoOutbox
from app.modules.sessions.models import EspacioAcademico, Sesion
from app.modules.sessions.schemas import ConvocadoEntrada
from app.modules.sessions.service import ServicioSesiones

TIEMPO_MAXIMO_MIN = 30


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def escenario_de_juego(db):
    inicio_prueba = ahora()
    dominio = obtener_configuracion().dominio_institucional
    docente = Usuario(
        nombre="Docente de prueba",
        correo=f"docente.{inicio_prueba.timestamp():.0f}@{dominio}",
        rol="DOCENTE",
        activo=True,
        correo_verificado=True,
        creado_en=inicio_prueba,
        actualizado_en=inicio_prueba,
    )
    db.add(docente)
    db.flush()

    caso = Caso(
        docente_creador_id=docente.id,
        nombre="Caso de juego",
        desarrollo_situacional="Desarrollo",
        contexto_historia="Historia",
        tiempo_estimado_min=TIEMPO_MAXIMO_MIN,
        estado="PUBLICADO",
        version=1,
        creado_en=inicio_prueba,
        actualizado_en=inicio_prueba,
    )
    escenario = Escenario(caso=caso, orden=1, titulo="Capítulo 1", contexto="Contexto")
    preguntas = []
    for numero in (1, 2):
        pregunta = Pregunta(escenario=escenario, orden=numero, enunciado=f"Pregunta {numero}")
        pregunta.opciones = [
            Opcion(
                pregunta=pregunta,
                orden=1,
                texto="Correcta",
                es_correcta=True,
                justificacion="Porque sí",
            ),
            Opcion(
                pregunta=pregunta,
                orden=2,
                texto="Incorrecta",
                es_correcta=False,
                justificacion="Porque no",
            ),
        ]
        preguntas.append(pregunta)
    rubrica = Rubrica(
        caso=caso,
        nombre="Rúbrica",
        escala_min=Decimal("0.00"),
        escala_max=Decimal("5.00"),
        nota_aprobatoria=Decimal("3.00"),
        publicada=True,
        creada_en=inicio_prueba,
        actualizada_en=inicio_prueba,
    )
    CriterioRubrica(
        rubrica=rubrica, orden=1, nombre="Criterio", peso=Decimal("100.00")
    ).preguntas = preguntas
    espacio = EspacioAcademico(nombre="Espacio", docente_id=docente.id, creado_en=inicio_prueba)
    db.add_all([caso, espacio])
    db.flush()

    sesion = Sesion(
        caso_id=caso.id,
        docente_id=docente.id,
        espacio_academico_id=espacio.id,
        inicio_programado=inicio_prueba,
        fin_programado=inicio_prueba + timedelta(hours=2),
        tiempo_maximo_min=TIEMPO_MAXIMO_MIN,
        estado="EN_CURSO",
        iniciada_en=inicio_prueba,
        creada_en=inicio_prueba,
    )
    db.add(sesion)
    db.commit()

    correo = f"estudiante.{inicio_prueba.timestamp():.0f}@{dominio}"
    convocatoria = ServicioSesiones(db).agregar_convocado(
        sesion,
        ConvocadoEntrada(correo=correo, nombre="Estudiante de prueba"),
        {"rol": "DOCENTE", "sub": docente.id},
    )
    estudiante = db.query(Usuario).filter(Usuario.correo == correo).one()
    datos = {
        "correo": correo,
        "codigo": descifrar(convocatoria.codigo_cifrado),
        "convocatoria_id": convocatoria.id,
        "caso_id": caso.id,
        "preguntas": [
            {
                "id": pregunta.id,
                "correcta": next(o.id for o in pregunta.opciones if o.es_correcta),
                "incorrecta": next(o.id for o in pregunta.opciones if not o.es_correcta),
            }
            for pregunta in preguntas
        ],
    }
    yield datos

    db.rollback()
    db.execute(delete(EventoOutbox).where(EventoOutbox.creado_en >= inicio_prueba))
    db.execute(delete(Sesion).where(Sesion.id == sesion.id))
    db.execute(delete(EspacioAcademico).where(EspacioAcademico.id == espacio.id))
    db.execute(delete(Caso).where(Caso.id == caso.id))
    db.execute(delete(Usuario).where(Usuario.id.in_([docente.id, estudiante.id])))
    db.commit()


def _cabeceras(cliente, datos) -> dict:
    respuesta = cliente.post(
        "/api/v1/auth/student-login",
        json={"correo": datos["correo"], "codigo": datos["codigo"]},
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['token_acceso']}"}


def test_el_estudiante_juega_un_caso_completo(cliente, escenario_de_juego) -> None:
    datos = escenario_de_juego
    cabeceras = _cabeceras(cliente, datos)

    inicio = cliente.post(
        f"/api/v1/participations/start/{datos['convocatoria_id']}", headers=cabeceras
    )
    assert inicio.status_code == 200, inicio.text
    participacion = inicio.json()
    assert participacion["estado"] == "EN_PROGRESO"
    assert participacion["progreso"]["segundos_restantes"] >= TIEMPO_MAXIMO_MIN * 60 - 60
    assert participacion["progreso"]["segundos_restantes"] <= TIEMPO_MAXIMO_MIN * 60

    pregunta_1, pregunta_2 = datos["preguntas"]
    for pregunta, opcion in ((pregunta_1, "correcta"), (pregunta_2, "incorrecta")):
        respuesta = cliente.put(
            f"/api/v1/participations/{participacion['id']}/answers/{pregunta['id']}",
            headers=cabeceras,
            json={"opcion_id": pregunta[opcion]},
        )
        assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["respondidas"] == 2

    # Retomar devuelve la misma participación (comparación con vence_en).
    retomada = cliente.post(
        f"/api/v1/participations/start/{datos['convocatoria_id']}", headers=cabeceras
    )
    assert retomada.status_code == 200, retomada.text
    assert retomada.json()["id"] == participacion["id"]
    assert len(retomada.json()["respuestas_actuales"]) == 2

    final = cliente.post(f"/api/v1/participations/{participacion['id']}/finish", headers=cabeceras)
    assert final.status_code == 200, final.text

    resultado = cliente.get(
        f"/api/v1/participations/{participacion['id']}/result", headers=cabeceras
    )
    assert resultado.status_code == 200, resultado.text
    cuerpo = resultado.json()
    assert (cuerpo["aciertos"], cuerpo["errores"], cuerpo["total_preguntas"]) == (1, 1, 2)
    assert Decimal(cuerpo["nota_final"]) == Decimal("2.50")
    assert {p["justificacion"] for p in cuerpo["preguntas"]} == {"Porque sí", "Porque no"}


def test_la_vista_del_estudiante_no_filtra_las_respuestas(cliente, escenario_de_juego) -> None:
    datos = escenario_de_juego
    cabeceras = _cabeceras(cliente, datos)

    vista = cliente.get(f"/api/v1/cases/{datos['caso_id']}/vista-estudiante", headers=cabeceras)

    assert vista.status_code == 200
    assert "es_correcta" not in vista.text
    assert "justificacion" not in vista.text
