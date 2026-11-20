from datetime import UTC, datetime, timedelta

from app.modules.participations.calculos import (
    calcular_limite_ingreso_tardio,
    calcular_vence_en,
    segundos_restantes,
)


def test_vence_en_gana_tiempo_maximo() -> None:
    iniciada = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    fin_sesion = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)

    resultado = calcular_vence_en(iniciada, 30, fin_sesion)

    assert resultado == iniciada + timedelta(minutes=30)


def test_vence_en_gana_fin_sesion() -> None:
    iniciada = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    fin_sesion = datetime(2026, 11, 20, 12, 20, tzinfo=UTC)

    resultado = calcular_vence_en(iniciada, 60, fin_sesion)

    assert resultado == fin_sesion


def test_limite_ingreso_tardio_usa_mitad_del_tiempo() -> None:
    iniciada = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    resultado = calcular_limite_ingreso_tardio(iniciada, 60, "0.5")

    assert resultado == iniciada + timedelta(minutes=30)


def test_segundos_restantes_no_es_negativo() -> None:
    ahora = datetime(2026, 11, 20, 13, 0, tzinfo=UTC)
    vence_en = datetime(2026, 11, 20, 12, 30, tzinfo=UTC)

    assert segundos_restantes(vence_en, ahora) == 0
