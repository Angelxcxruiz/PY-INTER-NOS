from datetime import datetime, timedelta
from decimal import Decimal


def calcular_limite_ingreso_tardio(
    iniciada_en: datetime,
    tiempo_maximo_min: int,
    fraccion: str,
) -> datetime:
    fraccion_decimal = Decimal(fraccion)
    minutos = Decimal(str(tiempo_maximo_min)) * fraccion_decimal
    segundos = int(minutos * Decimal("60"))
    return iniciada_en + timedelta(seconds=segundos)


def calcular_vence_en(
    iniciada_en: datetime,
    tiempo_maximo_min: int,
    fin_sesion: datetime,
) -> datetime:
    vence_por_tiempo = iniciada_en + timedelta(minutes=tiempo_maximo_min)
    return min(vence_por_tiempo, fin_sesion)


def segundos_restantes(vence_en: datetime, ahora: datetime) -> int:
    restante = int((vence_en - ahora).total_seconds())
    return max(0, restante)
