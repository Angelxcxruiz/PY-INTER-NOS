"""Triggers, vistas y migración 0012 contra MySQL real (Fase 12, requisito de Bases de Datos).

Estas pruebas dependen de la base de pruebas (TEST_DATABASE_URL) y de que esté en `head`.
Los servicios siguen validando en Python: aquí se prueba la segunda red de seguridad.
"""

import os
import subprocess
import sys
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.clock import ahora
from app.core.database import SessionLocal
from app.core.error_handlers import registrar_manejadores
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
from app.modules.sessions.models import Convocatoria, EspacioAcademico, Sesion

pytestmark = pytest.mark.integracion

MENSAJE_UNA_CORRECTA = "La pregunta ya tiene una opción correcta"
RAIZ = Path(__file__).resolve().parent.parent


def _id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def mundo(db):
    """Docente, dos convocados (uno verificado y con código vigente, otro no) y un caso."""
    momento = ahora()
    sufijo = uuid.uuid4().hex[:10]

    def usuario(rol: str, nombre: str, verificado: bool) -> Usuario:
        return Usuario(
            nombre=nombre,
            correo=f"{nombre.lower()}.{sufijo}@prueba.edu.co",
            rol=rol,
            activo=True,
            correo_verificado=verificado,
            creado_en=momento,
            actualizado_en=momento,
        )

    docente = usuario("DOCENTE", "Docente", True)
    ana = usuario("ESTUDIANTE", "Ana", True)
    beto = usuario("ESTUDIANTE", "Beto", False)
    db.add_all([docente, ana, beto])
    db.flush()

    caso = Caso(
        docente_creador_id=docente.id,
        nombre="Caso de triggers",
        desarrollo_situacional="Desarrollo",
        contexto_historia="Historia",
        tiempo_estimado_min=30,
        estado="PUBLICADO",
        version=1,
        creado_en=momento,
        actualizado_en=momento,
    )
    escenario = Escenario(caso=caso, orden=1, titulo="Capítulo 1", contexto="Contexto")
    preguntas = []
    for numero in (1, 2):
        pregunta = Pregunta(escenario=escenario, orden=numero, enunciado=f"Pregunta {numero}")
        pregunta.opciones = [
            Opcion(
                pregunta=pregunta, orden=1, texto="Correcta", es_correcta=True, justificacion="Sí"
            ),
            Opcion(
                pregunta=pregunta,
                orden=2,
                texto="Incorrecta",
                es_correcta=False,
                justificacion="No",
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
        creada_en=momento,
        actualizada_en=momento,
    )
    criterio = CriterioRubrica(
        rubrica=rubrica, orden=1, nombre="Criterio único", peso=Decimal("100.00")
    )
    criterio.preguntas = preguntas
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
    db.flush()
    conv_ana = Convocatoria(
        sesion_id=sesion.id,
        estudiante_id=ana.id,
        codigo_hash=_id().replace("-", "") * 2,
        codigo_vigente=True,
        creada_en=momento,
    )
    conv_beto = Convocatoria(
        sesion_id=sesion.id,
        estudiante_id=beto.id,
        codigo_hash=_id().replace("-", "") * 2,
        codigo_vigente=False,
        creada_en=momento,
    )
    db.add_all([conv_ana, conv_beto])
    db.commit()

    datos = {
        "docente_id": docente.id,
        "sesion_id": sesion.id,
        "caso_id": caso.id,
        "escenario_id": escenario.id,
        "conv_ana": conv_ana.id,
        "conv_beto": conv_beto.id,
        "criterio_id": criterio.id,
        "preguntas": [
            {
                "id": p.id,
                "correcta": next(o.id for o in p.opciones if o.es_correcta),
                "incorrecta": next(o.id for o in p.opciones if not o.es_correcta),
            }
            for p in preguntas
        ],
    }
    yield datos

    db.rollback()
    db.execute(
        text(
            "DELETE FROM auditoria_calificacion WHERE calificacion_id IN "
            "(SELECT id FROM calificacion WHERE participacion_id IN "
            "(SELECT p.id FROM participacion p WHERE p.convocatoria_id IN (:a, :b)) "
            "OR convocatoria_id IN (:a, :b))"
        ),
        {"a": conv_ana.id, "b": conv_beto.id},
    )
    db.execute(delete(EventoOutbox).where(EventoOutbox.creado_en >= momento))
    db.execute(delete(Sesion).where(Sesion.id == sesion.id))
    db.execute(delete(EspacioAcademico).where(EspacioAcademico.id == espacio.id))
    db.execute(delete(Caso).where(Caso.id == caso.id))
    db.execute(delete(Usuario).where(Usuario.id.in_([docente.id, ana.id, beto.id])))
    db.commit()


# --- utilidades SQL ---------------------------------------------------------------------


def _participacion(db, convocatoria_id, intento=1, estado="EN_PROGRESO", finalizada=None) -> str:
    identificador = _id()
    db.execute(
        text(
            "INSERT INTO participacion (id, convocatoria_id, numero_intento, iniciada_en, "
            "vence_en, finalizada_en, estado) VALUES (:id, :c, :n, UTC_TIMESTAMP(6), "
            "DATE_ADD(UTC_TIMESTAMP(6), INTERVAL 30 MINUTE), :f, :e)"
        ),
        {"id": identificador, "c": convocatoria_id, "n": intento, "f": finalizada, "e": estado},
    )
    db.commit()
    return identificador


def _respuesta(db, participacion_id, pregunta_id, opcion_id) -> str:
    identificador = _id()
    db.execute(
        text(
            "INSERT INTO respuesta (id, participacion_id, pregunta_id, opcion_id, "
            "respondida_en, actualizada_en) VALUES (:id, :p, :q, :o, UTC_TIMESTAMP(6), "
            "UTC_TIMESTAMP(6))"
        ),
        {"id": identificador, "p": participacion_id, "q": pregunta_id, "o": opcion_id},
    )
    db.commit()
    return identificador


def _calificacion(
    db, participacion_id=None, convocatoria_id=None, nota="2.50", ausencia=False
) -> str:
    identificador = _id()
    db.execute(
        text(
            "INSERT INTO calificacion (id, participacion_id, convocatoria_id, nota_final, "
            "puntaje_detalle, es_ausencia, es_parcial, calculada_en) VALUES (:id, :p, :c, :n, "
            "'{}', :a, 0, UTC_TIMESTAMP(6))"
        ),
        {
            "id": identificador,
            "p": participacion_id,
            "c": convocatoria_id,
            "n": nota,
            "a": ausencia,
        },
    )
    db.commit()
    return identificador


def _progreso(db, participacion_id):
    db.rollback()
    return db.execute(
        text(
            "SELECT respondidas, total_preguntas, porcentaje FROM progreso_participacion "
            "WHERE participacion_id = :p"
        ),
        {"p": participacion_id},
    ).one_or_none()


def _fila(db, consulta: str, **parametros):
    db.rollback()
    return db.execute(text(consulta), parametros).mappings().one()


# --- triggers ---------------------------------------------------------------------------


def test_una_sola_opcion_correcta_por_pregunta(db, mundo) -> None:
    pregunta_nueva = _id()
    db.execute(
        text(
            "INSERT INTO pregunta (id, escenario_id, orden, enunciado) VALUES (:i, :e, 3, 'Nueva')"
        ),
        {"i": pregunta_nueva, "e": mundo["escenario_id"]},
    )
    insertar = text(
        "INSERT INTO opcion (id, pregunta_id, orden, texto, es_correcta, justificacion) "
        "VALUES (:i, :p, :o, 'Texto', :c, 'Porque sí')"
    )
    # La primera correcta de una pregunta sin ninguna es el caso normal: pasa.
    db.execute(insertar, {"i": _id(), "p": pregunta_nueva, "o": 1, "c": 1})
    db.commit()

    with pytest.raises(OperationalError) as error:
        db.execute(insertar, {"i": _id(), "p": pregunta_nueva, "o": 2, "c": 1})
    db.rollback()
    assert MENSAJE_UNA_CORRECTA in str(error.value)

    # Una opción incorrecta sí se puede agregar.
    db.execute(insertar, {"i": _id(), "p": pregunta_nueva, "o": 2, "c": 0})
    db.commit()


def test_actualizar_no_permite_una_segunda_correcta_pero_no_se_bloquea_a_si_misma(
    db, mundo
) -> None:
    pregunta = mundo["preguntas"][0]

    # Reescribir la propia opción correcta (incluso marcándola otra vez) es legítimo.
    db.execute(
        text("UPDATE opcion SET texto = 'Editada', es_correcta = 1 WHERE id = :i"),
        {"i": pregunta["correcta"]},
    )
    db.commit()

    with pytest.raises(OperationalError) as error:
        db.execute(
            text("UPDATE opcion SET es_correcta = 1 WHERE id = :i"), {"i": pregunta["incorrecta"]}
        )
    db.rollback()
    assert MENSAJE_UNA_CORRECTA in str(error.value)

    # Cambiar cuál es la correcta, en el orden seguro (primero desmarcar), funciona.
    db.execute(text("UPDATE opcion SET es_correcta = 0 WHERE id = :i"), {"i": pregunta["correcta"]})
    db.execute(
        text("UPDATE opcion SET es_correcta = 1 WHERE id = :i"), {"i": pregunta["incorrecta"]}
    )
    db.commit()


def test_la_regla_del_trigger_llega_al_cliente_como_409() -> None:
    aplicacion = FastAPI()
    registrar_manejadores(aplicacion)

    @aplicacion.get("/regla")
    def regla() -> None:
        raise DBAPIError("INSERT", {}, Exception(1644, MENSAJE_UNA_CORRECTA))

    @aplicacion.get("/otro")
    def otro() -> None:
        raise DBAPIError("INSERT", {}, Exception(1062, "Duplicado secreto"))

    cliente = TestClient(aplicacion, raise_server_exceptions=False)
    respuesta = cliente.get("/regla")
    otra = cliente.get("/otro")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"]["mensaje"] == MENSAJE_UNA_CORRECTA
    assert otra.status_code == 500
    assert "secreto" not in otra.text


def test_la_calificacion_se_audita_al_crear_cambiar_y_borrar(db, mundo) -> None:
    participacion = _participacion(db, mundo["conv_ana"], estado="FINALIZADA")
    calificacion = _calificacion(db, participacion_id=participacion, nota="2.50")

    db.execute(text("UPDATE calificacion SET nota_final = 4.00 WHERE id = :i"), {"i": calificacion})
    # Cambiar otra columna no genera auditoría: solo importa la nota.
    db.execute(text("UPDATE calificacion SET es_parcial = 1 WHERE id = :i"), {"i": calificacion})
    db.execute(text("DELETE FROM calificacion WHERE id = :i"), {"i": calificacion})
    db.commit()

    filas = db.execute(
        text(
            "SELECT accion, nota_anterior, nota_nueva, usuario_bd FROM auditoria_calificacion "
            "WHERE calificacion_id = :i ORDER BY fecha, accion DESC"
        ),
        {"i": calificacion},
    ).all()
    por_accion = {fila.accion: fila for fila in filas}

    assert len(filas) == 3
    assert (por_accion["INSERT"].nota_anterior, por_accion["INSERT"].nota_nueva) == (
        None,
        Decimal("2.50"),
    )
    assert (por_accion["UPDATE"].nota_anterior, por_accion["UPDATE"].nota_nueva) == (
        Decimal("2.50"),
        Decimal("4.00"),
    )
    assert (por_accion["DELETE"].nota_anterior, por_accion["DELETE"].nota_nueva) == (
        Decimal("4.00"),
        None,
    )
    assert all(fila.usuario_bd for fila in filas)
    db.execute(
        text("DELETE FROM auditoria_calificacion WHERE calificacion_id = :i"), {"i": calificacion}
    )
    db.commit()


def test_el_progreso_se_actualiza_solo_al_insertar_cambiar_y_borrar_respuestas(db, mundo) -> None:
    participacion = _participacion(db, mundo["conv_ana"])
    p1, p2 = mundo["preguntas"]

    assert _progreso(db, participacion) is None
    primera = _respuesta(db, participacion, p1["id"], p1["correcta"])
    inicial = _progreso(db, participacion)
    assert (inicial.respondidas, inicial.total_preguntas, inicial.porcentaje) == (
        1,
        2,
        Decimal("50.00"),
    )

    segunda = _respuesta(db, participacion, p2["id"], p2["incorrecta"])
    assert _progreso(db, participacion).respondidas == 2
    assert _progreso(db, participacion).porcentaje == Decimal("100.00")

    # Cambiar la opción elegida no cambia el conteo, pero el trigger de UPDATE debe correr.
    db.execute(
        text("UPDATE respuesta SET opcion_id = :o WHERE id = :i"),
        {"o": p2["correcta"], "i": segunda},
    )
    db.commit()
    assert _progreso(db, participacion).respondidas == 2

    db.execute(text("DELETE FROM respuesta WHERE id = :i"), {"i": primera})
    db.commit()
    final = _progreso(db, participacion)
    assert (final.respondidas, final.porcentaje) == (1, Decimal("50.00"))


def test_finalizar_una_participacion_llena_finalizada_en_sola_sin_pisar_la_existente(
    db, mundo
) -> None:
    abierta = _participacion(db, mundo["conv_ana"], intento=1)
    con_fecha = _participacion(db, mundo["conv_beto"], intento=1)
    consulta = "SELECT finalizada_en, UTC_TIMESTAMP(6) AS ahora FROM participacion WHERE id = :i"

    db.execute(text("UPDATE participacion SET estado = 'FINALIZADA' WHERE id = :i"), {"i": abierta})
    db.execute(
        text(
            "UPDATE participacion SET estado = 'EXPIRADA', "
            "finalizada_en = '2020-01-01 10:00:00.000000' WHERE id = :i"
        ),
        {"i": con_fecha},
    )
    db.commit()

    llenada = _fila(db, consulta, i=abierta)
    respetada = _fila(db, consulta, i=con_fecha)
    assert llenada["finalizada_en"] is not None
    assert abs((llenada["ahora"] - llenada["finalizada_en"]).total_seconds()) < 60
    assert respetada["finalizada_en"].year == 2020

    # Un cambio que no es de estado terminal no inventa la fecha.
    otra = _participacion(db, mundo["conv_ana"], intento=2)
    db.execute(text("UPDATE participacion SET motivo_cierre = 'X' WHERE id = :i"), {"i": otra})
    db.commit()
    assert _fila(db, consulta, i=otra)["finalizada_en"] is None


# --- vistas -----------------------------------------------------------------------------


def test_notas_por_sesion_incluye_al_que_no_participo_con_nota_nula(db, mundo) -> None:
    participacion = _participacion(db, mundo["conv_ana"], estado="FINALIZADA")
    _calificacion(db, participacion_id=participacion, nota="4.00")

    db.rollback()
    filas = db.execute(
        text(
            "SELECT estudiante_nombre, estado_participacion, nota_final, es_ausencia, "
            "numero_intentos FROM vista_notas_por_sesion WHERE sesion_id = :s"
        ),
        {"s": mundo["sesion_id"]},
    ).all()
    por_nombre = {fila.estudiante_nombre: fila for fila in filas}

    assert len(filas) == 2
    assert por_nombre["Ana"].nota_final == Decimal("4.00")
    assert por_nombre["Ana"].numero_intentos == 1
    assert por_nombre["Beto"].nota_final is None
    assert por_nombre["Beto"].estado_participacion == "NO_INICIO"
    assert por_nombre["Beto"].numero_intentos == 0


def test_estadisticas_por_criterio_sin_respuestas_da_porcentaje_nulo(db, mundo) -> None:
    consulta = (
        "SELECT peso, numero_preguntas, aciertos, total_respuestas, porcentaje_acierto "
        "FROM vista_estadisticas_por_criterio WHERE criterio_id = :c"
    )
    sin_datos = _fila(db, consulta, c=mundo["criterio_id"])
    assert sin_datos["total_respuestas"] == 0
    assert sin_datos["porcentaje_acierto"] is None
    assert (sin_datos["peso"], sin_datos["numero_preguntas"]) == (Decimal("100.00"), 2)

    p1, p2 = mundo["preguntas"]
    cerrada = _participacion(db, mundo["conv_ana"], estado="FINALIZADA")
    _respuesta(db, cerrada, p1["id"], p1["correcta"])
    _respuesta(db, cerrada, p2["id"], p2["incorrecta"])
    # Las respuestas de una participación abierta no cuentan todavía.
    abierta = _participacion(db, mundo["conv_beto"])
    _respuesta(db, abierta, p1["id"], p1["correcta"])

    con_datos = _fila(db, consulta, c=mundo["criterio_id"])
    assert (con_datos["aciertos"], con_datos["total_respuestas"]) == (1, 2)
    assert con_datos["porcentaje_acierto"] == Decimal("50.00")


def test_convocados_estado_refleja_codigo_vigente_y_correo_verificado(db, mundo) -> None:
    consulta = (
        "SELECT codigo_vigente, correo_verificado, total_participaciones, tiene_calificacion, "
        "es_ausencia FROM vista_convocados_estado WHERE convocatoria_id = :c"
    )
    ana = _fila(db, consulta, c=mundo["conv_ana"])
    beto = _fila(db, consulta, c=mundo["conv_beto"])
    assert (ana["codigo_vigente"], ana["correo_verificado"]) == (1, 1)
    assert (beto["codigo_vigente"], beto["correo_verificado"]) == (0, 0)
    assert (beto["total_participaciones"], beto["tiene_calificacion"], beto["es_ausencia"]) == (
        0,
        0,
        0,
    )

    _calificacion(db, convocatoria_id=mundo["conv_beto"], nota="0.00", ausencia=True)
    beto = _fila(db, consulta, c=mundo["conv_beto"])
    assert (beto["tiene_calificacion"], beto["es_ausencia"]) == (1, 1)


def test_participaciones_detalle_es_de_solo_lectura_y_dice_si_acerto(db, mundo) -> None:
    participacion = _participacion(db, mundo["conv_ana"], estado="FINALIZADA")
    p1, p2 = mundo["preguntas"]
    _respuesta(db, participacion, p1["id"], p1["correcta"])
    _respuesta(db, participacion, p2["id"], p2["incorrecta"])

    db.rollback()
    filas = db.execute(
        text(
            "SELECT orden_pregunta, respondida, acerto, opcion_elegida, opcion_correcta "
            "FROM vista_participaciones_detalle WHERE participacion_id = :p ORDER BY orden_pregunta"
        ),
        {"p": participacion},
    ).all()
    assert [(f.orden_pregunta, f.respondida, f.acerto) for f in filas] == [(1, 1, 1), (2, 1, 0)]
    assert filas[1].opcion_elegida == "Incorrecta"
    assert filas[1].opcion_correcta == "Correcta"

    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE vista_participaciones_detalle SET enunciado = 'X'"))
    db.rollback()


def test_resumen_docente_cuenta_casos_sesiones_y_calificadas(db, mundo) -> None:
    consulta = "SELECT * FROM vista_resumen_docente WHERE docente_id = :d"
    antes = _fila(db, consulta, d=mundo["docente_id"])
    assert (antes["casos_publicados"], antes["casos_borrador"], antes["casos_archivados"]) == (
        1,
        0,
        0,
    )
    assert (antes["sesiones_en_curso"], antes["sesiones_finalizadas"]) == (1, 0)
    assert antes["participaciones_calificadas"] == 0

    participacion = _participacion(db, mundo["conv_ana"], estado="FINALIZADA")
    _calificacion(db, participacion_id=participacion)
    assert _fila(db, consulta, d=mundo["docente_id"])["participaciones_calificadas"] == 1


# --- migración --------------------------------------------------------------------------


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


def _objetos(db) -> dict[str, int]:
    db.rollback()
    return {
        "triggers": db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME LIKE 'trg_%'"
            )
        ).scalar(),
        "vistas": db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.VIEWS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE 'vista_%'"
            )
        ).scalar(),
        "tablas": db.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME IN ('auditoria_calificacion', 'progreso_participacion')"
            )
        ).scalar(),
    }


def test_la_migracion_sube_baja_y_vuelve_a_subir_sin_errores(db) -> None:
    assert _objetos(db) == {"triggers": 9, "vistas": 5, "tablas": 2}
    db.close()
    try:
        _alembic("downgrade", "0011_verificacion_registro")
        with SessionLocal() as sesion:
            assert _objetos(sesion) == {"triggers": 0, "vistas": 0, "tablas": 0}
    finally:
        _alembic("upgrade", "head")
    with SessionLocal() as sesion:
        assert _objetos(sesion) == {"triggers": 9, "vistas": 5, "tablas": 2}
