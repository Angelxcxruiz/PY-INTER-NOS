from datetime import UTC, datetime
from decimal import Decimal

from app.modules.cases.models import (
    Caso,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Rubrica,
)
from app.modules.cases.schemas import CasoEstudianteSalida
from app.modules.cases.validacion import validar_caso_para_publicar


def crear_caso_valido() -> Caso:
    momento = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    caso = Caso(
        id="caso-1",
        docente_creador_id="docente-1",
        nombre="Caso valido",
        desarrollo_situacional="Desarrollo",
        contexto_historia="Contexto",
        tiempo_estimado_min=30,
        estado="BORRADOR",
        version=1,
        creado_en=momento,
        actualizado_en=momento,
    )
    escenario = Escenario(
        id="escenario-1",
        caso=caso,
        orden=1,
        titulo="Escenario",
        contexto="Contexto",
    )
    pregunta = Pregunta(
        id="pregunta-1",
        escenario=escenario,
        orden=1,
        enunciado="Pregunta",
    )
    pregunta.opciones = [
        Opcion(
            id="opcion-1",
            pregunta=pregunta,
            orden=1,
            texto="Correcta",
            es_correcta=True,
            justificacion="Justificacion correcta",
        ),
        Opcion(
            id="opcion-2",
            pregunta=pregunta,
            orden=2,
            texto="Incorrecta",
            es_correcta=False,
            justificacion="Justificacion incorrecta",
        ),
    ]
    rubrica = Rubrica(
        id="rubrica-1",
        caso=caso,
        nombre="Rubrica",
        escala_min=Decimal("0"),
        escala_max=Decimal("5"),
        nota_aprobatoria=Decimal("3"),
        publicada=False,
        creada_en=momento,
        actualizada_en=momento,
    )
    criterio = CriterioRubrica(
        id="criterio-1",
        rubrica=rubrica,
        orden=1,
        nombre="Criterio",
        peso=Decimal("100"),
    )
    criterio.preguntas = [pregunta]
    return caso


def test_caso_valido_da_lista_vacia() -> None:
    assert validar_caso_para_publicar(crear_caso_valido()) == []


def test_validacion_acumula_todos_los_errores() -> None:
    caso = crear_caso_valido()
    pregunta = caso.escenarios[0].preguntas[0]
    pregunta.opciones[0].es_correcta = False

    segunda_opcion = pregunta.opciones[1]
    segunda_opcion.es_correcta = False
    segunda_opcion.justificacion = ""

    caso.rubrica.criterios[0].peso = Decimal("90")
    caso.rubrica.criterios[0].preguntas = []

    codigos = {error.codigo for error in validar_caso_para_publicar(caso)}

    assert "PREGUNTA_CORRECTAS_INVALIDAS" in codigos
    assert "OPCION_SIN_JUSTIFICACION" in codigos
    assert "RUBRICA_PESO_INVALIDO" in codigos
    assert "PREGUNTA_NO_CUBIERTA" in codigos


def test_vista_estudiante_no_expone_campos_sensibles() -> None:
    caso = crear_caso_valido()
    salida = CasoEstudianteSalida.model_validate(caso)
    contenido = salida.model_dump(mode="json")

    def recorrer(valor) -> None:
        if isinstance(valor, dict):
            assert "es_correcta" not in valor
            assert "justificacion" not in valor
            for hijo in valor.values():
                recorrer(hijo)
        elif isinstance(valor, list):
            for hijo in valor:
                recorrer(hijo)

    recorrer(contenido)
