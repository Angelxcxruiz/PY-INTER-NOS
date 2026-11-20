from decimal import Decimal

from app.modules.reports.csv_export import escapar_csv, generar_csv
from app.modules.reports.estadisticas import (
    distribucion_por_rangos,
    maximo,
    mediana,
    minimo,
    promedio,
    resumen_registros,
    tasa,
)


def test_promedio_vacio_y_conocido() -> None:
    assert promedio([]) is None
    assert promedio([Decimal("3"), Decimal("4")]) == Decimal("3.50")


def test_mediana_impar_y_par() -> None:
    assert mediana([Decimal("1"), Decimal("3"), Decimal("2")]) == Decimal("2.00")
    assert mediana([Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")]) == Decimal("2.50")


def test_minimo_maximo_vacios() -> None:
    assert minimo([]) is None
    assert maximo([]) is None


def test_tasa_cero_y_tasa_conocida() -> None:
    assert tasa(0, 0) is None
    assert tasa(3, 4) == Decimal("75.00")


def test_distribucion_maximo_en_ultimo_bloque() -> None:
    rangos = distribucion_por_rangos(
        [Decimal("0"), Decimal("5")],
        Decimal("0"),
        Decimal("5"),
    )
    assert rangos[0]["cantidad"] == 1
    assert rangos[4]["cantidad"] == 1


def test_resumen_sin_registros() -> None:
    resumen = resumen_registros([])
    assert resumen["total_convocados"] == 0
    assert resumen["tasa_participacion"] is None
    assert resumen["promedio"] is None


def test_todos_ausentes_tasas() -> None:
    registros = [
        {"estado": "AUSENTE", "nota_final": None},
        {"estado": "AUSENTE", "nota_final": None},
    ]
    resumen = resumen_registros(registros)
    assert resumen["tasa_ausencia"] == Decimal("100.00")
    assert resumen["tasa_participacion"] == Decimal("0.00")


def test_escapado_csv() -> None:
    assert escapar_csv("=1+1").startswith("'")
    assert escapar_csv("+34").startswith("'")
    assert escapar_csv("-5").startswith("'")
    assert escapar_csv("@dato").startswith("'")
    assert escapar_csv("Ana") == "Ana"


def test_csv_empieza_con_bom() -> None:
    contenido = b"".join(generar_csv(["nombre", "nota"], [["Ana", Decimal("5.00")]]))
    assert contenido.startswith(b"\xef\xbb\xbf")
    assert b";" in contenido


def test_todos_los_numeros_estadisticos_son_decimal() -> None:
    valor = tasa(3, 4)
    assert isinstance(valor, Decimal)
