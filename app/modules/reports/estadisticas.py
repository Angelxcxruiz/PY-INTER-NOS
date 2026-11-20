from decimal import ROUND_HALF_UP, Decimal
from statistics import median

CERO = Decimal("0")
CIENTO = Decimal("100")
DOS_DECIMALES = Decimal("0.01")


def redondear_decimal(valor: Decimal) -> Decimal:
    return valor.quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def promedio(valores: list[Decimal]) -> Decimal | None:
    if not valores:
        return None
    suma = sum((Decimal(str(valor)) for valor in valores), CERO)
    return redondear_decimal(suma / Decimal(len(valores)))


def mediana(valores: list[Decimal]) -> Decimal | None:
    if not valores:
        return None
    ordenados = sorted(Decimal(str(valor)) for valor in valores)
    return redondear_decimal(Decimal(str(median(ordenados))))


def minimo(valores: list[Decimal]) -> Decimal | None:
    if not valores:
        return None
    return redondear_decimal(min(Decimal(str(valor)) for valor in valores))


def maximo(valores: list[Decimal]) -> Decimal | None:
    if not valores:
        return None
    return redondear_decimal(max(Decimal(str(valor)) for valor in valores))


def tasa(parte: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    valor = (Decimal(parte) / Decimal(total)) * CIENTO
    return redondear_decimal(valor)


def distribucion_por_rangos(
    valores: list[Decimal],
    escala_min: Decimal,
    escala_max: Decimal,
) -> list[dict]:
    if escala_max <= escala_min:
        return [{"desde": escala_min, "hasta": escala_max, "cantidad": 0} for _ in range(5)]
    ancho = (escala_max - escala_min) / Decimal("5")
    rangos = []
    for indice in range(5):
        desde = escala_min + ancho * Decimal(indice)
        hasta = escala_min + ancho * Decimal(indice + 1)
        rangos.append({"desde": desde, "hasta": hasta, "cantidad": 0})

    for valor in valores:
        nota = Decimal(str(valor))
        if nota >= escala_max:
            indice = 4
        elif nota <= escala_min:
            indice = 0
        else:
            indice = int((nota - escala_min) // ancho)
            indice = min(indice, 4)
        rangos[indice]["cantidad"] += 1
    return rangos


def resumen_registros(registros: list[dict]) -> dict:
    total = len(registros)
    participaciones = sum(
        1
        for registro in registros
        if registro.get("estado")
        in {
            "EN_PROGRESO",
            "FINALIZO",
            "EXPIRA",
            "CERRADA_POR_SESION",
        }
    )
    finalizaciones = sum(1 for registro in registros if registro.get("estado") == "FINALIZO")
    expiraciones = sum(
        1 for registro in registros if registro.get("estado") in {"EXPIRA", "CERRADA_POR_SESION"}
    )
    ausencias = sum(1 for registro in registros if registro.get("estado") == "AUSENTE")
    notas = [
        Decimal(str(registro["nota_final"]))
        for registro in registros
        if registro.get("nota_final") is not None
    ]
    return {
        "total_convocados": total,
        "tasa_participacion": tasa(participaciones, total),
        "tasa_finalizacion": tasa(finalizaciones, total),
        "tasa_expiracion": tasa(expiraciones, total),
        "tasa_ausencia": tasa(ausencias, total),
        "promedio": promedio(notas),
        "mediana": mediana(notas),
        "nota_minima": minimo(notas),
        "nota_maxima": maximo(notas),
    }
