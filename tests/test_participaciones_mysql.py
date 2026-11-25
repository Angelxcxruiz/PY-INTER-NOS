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
    dominio = obtener_configuracion().dominio_principal
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
        "docente_id": docente.id,
        "sesion_id": sesion.id,
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


def _cabeceras_docente(datos) -> dict:
    from app.core.security import crear_jwt

    token = crear_jwt(
        {
            "sub": datos["docente_id"],
            "rol": "DOCENTE",
            "permisos": ["CREAR_CASOS"],
            "estado_cuenta": "ACTIVO",
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _juega_y_finaliza(cliente, datos) -> str:
    cabeceras = _cabeceras(cliente, datos)
    inicio = cliente.post(
        f"/api/v1/participations/start/{datos['convocatoria_id']}", headers=cabeceras
    )
    participacion_id = inicio.json()["id"]
    pregunta = datos["preguntas"][0]
    cliente.put(
        f"/api/v1/participations/{participacion_id}/answers/{pregunta['id']}",
        headers=cabeceras,
        json={"opcion_id": pregunta["correcta"]},
    )
    cliente.post(f"/api/v1/participations/{participacion_id}/finish", headers=cabeceras)
    return participacion_id


def test_el_catalogo_de_casos_publicados_exige_sesion_y_no_filtra_respuestas(
    cliente, escenario_de_juego
) -> None:
    sin_token = cliente.get("/api/v1/cases/publicados")
    con_token = cliente.get(
        "/api/v1/cases/publicados", headers=_cabeceras(cliente, escenario_de_juego)
    )

    assert sin_token.status_code == 401
    assert con_token.status_code == 200
    assert "es_correcta" not in con_token.text
    assert "justificacion" not in con_token.text


def test_el_docente_dueno_ve_el_resultado_y_otro_docente_no(cliente, escenario_de_juego) -> None:
    datos = escenario_de_juego
    participacion_id = _juega_y_finaliza(cliente, datos)
    dueno = _cabeceras_docente(datos)
    ajeno = _cabeceras_docente({**datos, "docente_id": "00000000-0000-0000-0000-000000000000"})

    por_participacion = cliente.get(
        f"/api/v1/participations/{participacion_id}/result", headers=dueno
    )
    por_convocatoria = cliente.get(
        f"/api/v1/convocatorias/{datos['convocatoria_id']}/result", headers=dueno
    )
    de_otro = cliente.get(f"/api/v1/convocatorias/{datos['convocatoria_id']}/result", headers=ajeno)

    assert por_participacion.status_code == 200, por_participacion.text
    assert por_convocatoria.status_code == 200, por_convocatoria.text
    assert por_participacion.json()["aciertos"] == 1
    assert de_otro.status_code == 403


def test_el_estudiante_lee_la_retroalimentacion_que_le_escribio_el_docente(
    cliente, escenario_de_juego
) -> None:
    datos = escenario_de_juego
    participacion_id = _juega_y_finaliza(cliente, datos)

    guardada = cliente.post(
        f"/api/v1/participations/{participacion_id}/retroalimentacion",
        headers=_cabeceras_docente(datos),
        json={"texto": "Buen análisis, revisa la pregunta 2."},
    )
    resultado = cliente.get(
        f"/api/v1/participations/{participacion_id}/result",
        headers=_cabeceras(cliente, datos),
    )

    assert guardada.status_code == 200, guardada.text
    assert resultado.json()["retroalimentacion"] == "Buen análisis, revisa la pregunta 2."


def test_la_repeticion_solo_se_autoriza_con_la_sesion_en_curso(
    cliente, db, escenario_de_juego
) -> None:
    datos = escenario_de_juego
    dueno = _cabeceras_docente(datos)
    ruta = f"/api/v1/participations/convocatorias/{datos['convocatoria_id']}/autorizar-repeticion"

    en_curso = cliente.post(ruta, headers=dueno, json={"motivo": "Se cayó la conexión"})
    db.execute(
        Sesion.__table__.update().where(Sesion.id == datos["sesion_id"]).values(estado="FINALIZADO")
    )
    db.commit()
    finalizada = cliente.post(ruta, headers=dueno, json={"motivo": "Tarde"})

    assert en_curso.status_code == 200, en_curso.text
    assert finalizada.status_code == 409
    assert finalizada.json()["error"]["detalles"]["estado_actual"] == "FINALIZADO"
