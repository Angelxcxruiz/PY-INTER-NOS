import csv
import io
from collections.abc import Iterable, Iterator

from app.core.config import obtener_configuracion


def escapar_csv(valor) -> str:
    texto = "" if valor is None else str(valor)
    if texto.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + texto
    return texto


def generar_csv(
    encabezados: list[str],
    filas: Iterable[list],
) -> Iterator[bytes]:
    separador = obtener_configuracion().csv_separador
    yield "\ufeff".encode("utf-8")
    buffer = io.StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=separador, lineterminator="\r\n")
    escritor.writerow(encabezados)
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)
    for fila in filas:
        escritor.writerow([escapar_csv(valor) for valor in fila])
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
