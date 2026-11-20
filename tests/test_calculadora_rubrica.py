from decimal import Decimal

from app.modules.evaluations.calculadora import (
    CalculadoraRubrica,
    CriterioCalculado,
    PreguntaCalculada,
    RubricaCalculada,
)


def calculadora(
    aciertos: int,
    total: int,
    escala_min: str = "0",
    escala_max: str = "5",
    criterios: tuple[CriterioCalculado, ...] | None = None,
) -> dict:
    preguntas = tuple(
        PreguntaCalculada(
            id=f"p{i}",
            opcion_correcta_id=f"o{i}",
        )
        for i in range(total)
    )
    respuestas = {f"p{i}": f"o{i}" if i < aciertos else f"mala{i}" for i in range(total)}
    if criterios is None:
        criterios = (
            CriterioCalculado(
                id="c1",
                nombre="General",
                peso=Decimal("100"),
                pregunta_ids=tuple(p.id for p in preguntas),
            ),
        )
    rubrica = RubricaCalculada(
        escala_min=Decimal(escala_min),
        escala_max=Decimal(escala_max),
        nota_aprobatoria=Decimal("3"),
        criterios=criterios,
    )
    return CalculadoraRubrica(list(preguntas), respuestas, rubrica).calcular()


def test_todo_correcto_da_nota_maxima() -> None:
    resultado = calculadora(4, 4)
    assert resultado["nota_final"] == Decimal("5.00")


def test_todo_incorrecto_da_nota_minima() -> None:
    resultado = calculadora(0, 4)
    assert resultado["nota_final"] == Decimal("0.00")


def test_mitad_aciertos_da_nota_intermedia() -> None:
    resultado = calculadora(2, 4)
    assert resultado["nota_final"] == Decimal("2.50")


def test_dos_criterios_60_40_aporta_por_criterio() -> None:
    preguntas = tuple(PreguntaCalculada(id=f"p{i}", opcion_correcta_id=f"o{i}") for i in range(5))
    respuestas = {f"p{i}": f"o{i}" for i in range(3)}
    criterios = (
        CriterioCalculado("c1", "Primero", Decimal("60"), tuple(p.id for p in preguntas[:3])),
        CriterioCalculado("c2", "Segundo", Decimal("40"), tuple(p.id for p in preguntas[3:])),
    )
    rubrica = RubricaCalculada(
        Decimal("0"),
        Decimal("5"),
        Decimal("3"),
        criterios,
    )
    resultado = CalculadoraRubrica(list(preguntas), respuestas, rubrica).calcular()

    assert resultado["porcentaje"] == Decimal("60.000000")
    assert resultado["nota_final"] == Decimal("3.00")
    assert resultado["puntaje_detalle"][0]["aporte"] == Decimal("60")
    assert resultado["puntaje_detalle"][1]["aporte"] == Decimal("0")


def test_redondeo_round_half_up() -> None:
    resultado = calculadora(5, 8)
    assert resultado["nota_final"] == Decimal("3.13")


def test_preguntas_no_cubiertas_no_dividen_por_cero() -> None:
    resultado = calculadora(1, 3)
    assert resultado["nota_final"] == Decimal("1.67")


def test_criterio_sin_preguntas_asignadas_aporta_cero() -> None:
    criterios = (CriterioCalculado("c1", "Sin preguntas", Decimal("100"), tuple()),)
    resultado = calculadora(4, 4, criterios=criterios)
    assert resultado["nota_final"] == Decimal("0.00")
    assert resultado["puntaje_detalle"][0]["aporte"] == Decimal("0")


def test_escala_distinta_a_estandar() -> None:
    resultado = calculadora(3, 3, escala_max="100")
    assert resultado["nota_final"] == Decimal("100.00")


def test_pregunta_sin_respuesta_es_error_y_es_parcial() -> None:
    preguntas = tuple(PreguntaCalculada(id=f"p{i}", opcion_correcta_id=f"o{i}") for i in range(3))
    respuestas = {"p0": "o0", "p1": "o1"}
    criterios = (
        CriterioCalculado(
            "c1",
            "General",
            Decimal("100"),
            tuple(p.id for p in preguntas),
        ),
    )
    rubrica = RubricaCalculada(
        Decimal("0"),
        Decimal("5"),
        Decimal("3"),
        criterios,
    )
    resultado = CalculadoraRubrica(list(preguntas), respuestas, rubrica).calcular()

    assert resultado["errores"] == 1
    assert resultado["es_parcial"] is True


def test_nota_final_es_decimal() -> None:
    resultado = calculadora(1, 2)
    assert isinstance(resultado["nota_final"], Decimal)
