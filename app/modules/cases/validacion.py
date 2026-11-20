from decimal import Decimal

from app.modules.cases.models import Caso
from app.modules.cases.schemas import ErrorValidacionSalida


def validar_caso_para_publicar(caso: Caso) -> list[ErrorValidacionSalida]:
    errores: list[ErrorValidacionSalida] = []
    ubicacion_caso = "caso"

    if not caso.nombre or not caso.nombre.strip():
        errores.append(
            ErrorValidacionSalida(
                codigo="CASO_NOMBRE_VACIO",
                mensaje="El nombre del caso no puede estar vacio",
                ubicacion=ubicacion_caso,
            )
        )
    if caso.tiempo_estimado_min <= 0:
        errores.append(
            ErrorValidacionSalida(
                codigo="TIEMPO_INVALIDO",
                mensaje="El tiempo estimado debe ser mayor que cero",
                ubicacion="tiempo_estimado_min",
            )
        )
    if not caso.escenarios:
        errores.append(
            ErrorValidacionSalida(
                codigo="CASO_SIN_ESCENARIOS",
                mensaje="El caso debe tener al menos un escenario",
                ubicacion="caso",
            )
        )

    ids_preguntas = set()
    ids_cubiertas = set()

    for indice_escenario, escenario in enumerate(caso.escenarios, start=1):
        ubicacion_escenario = f"escenario[{indice_escenario}]"
        if not escenario.titulo or not escenario.titulo.strip():
            errores.append(
                ErrorValidacionSalida(
                    codigo="ESCENARIO_SIN_TITULO",
                    mensaje="El escenario debe tener titulo",
                    ubicacion=ubicacion_escenario,
                )
            )
        if not escenario.contexto or not escenario.contexto.strip():
            errores.append(
                ErrorValidacionSalida(
                    codigo="ESCENARIO_SIN_CONTEXTO",
                    mensaje="El escenario debe tener contexto",
                    ubicacion=ubicacion_escenario,
                )
            )
        if not escenario.preguntas:
            errores.append(
                ErrorValidacionSalida(
                    codigo="ESCENARIO_SIN_PREGUNTAS",
                    mensaje="El escenario debe tener al menos una pregunta",
                    ubicacion=ubicacion_escenario,
                )
            )

        for indice_pregunta, pregunta in enumerate(escenario.preguntas, start=1):
            ubicacion_pregunta = f"{ubicacion_escenario}.pregunta[{indice_pregunta}]"
            ids_preguntas.add(pregunta.id)
            if len(pregunta.opciones) < 2:
                errores.append(
                    ErrorValidacionSalida(
                        codigo="PREGUNTA_OPCIONES_INSUFICIENTES",
                        mensaje="La pregunta debe tener al menos dos opciones",
                        ubicacion=ubicacion_pregunta,
                    )
                )

            correctas = [opcion for opcion in pregunta.opciones if opcion.es_correcta]
            if len(correctas) != 1:
                errores.append(
                    ErrorValidacionSalida(
                        codigo="PREGUNTA_CORRECTAS_INVALIDAS",
                        mensaje="La pregunta debe tener exactamente una opcion correcta",
                        ubicacion=ubicacion_pregunta,
                    )
                )

            for indice_opcion, opcion in enumerate(pregunta.opciones, start=1):
                if not opcion.justificacion or not opcion.justificacion.strip():
                    errores.append(
                        ErrorValidacionSalida(
                            codigo="OPCION_SIN_JUSTIFICACION",
                            mensaje="Toda opcion debe tener justificacion",
                            ubicacion=f"{ubicacion_pregunta}.opcion[{indice_opcion}]",
                        )
                    )

    rubrica = caso.rubrica
    if rubrica is None:
        errores.append(
            ErrorValidacionSalida(
                codigo="CASO_SIN_RUBRICA",
                mensaje="El caso debe tener una rubrica",
                ubicacion="rubrica",
            )
        )
        return errores

    if not rubrica.criterios:
        errores.append(
            ErrorValidacionSalida(
                codigo="RUBRICA_SIN_CRITERIOS",
                mensaje="La rubrica debe tener al menos un criterio",
                ubicacion="rubrica",
            )
        )

    suma_pesos = sum(
        (Decimal(str(criterio.peso)) for criterio in rubrica.criterios),
        start=Decimal("0"),
    )
    if suma_pesos != Decimal("100"):
        errores.append(
            ErrorValidacionSalida(
                codigo="RUBRICA_PESO_INVALIDO",
                mensaje="Los pesos de la rubrica deben sumar exactamente 100",
                ubicacion="rubrica",
            )
        )

    for criterio in rubrica.criterios:
        ids_cubiertas.update(pregunta.id for pregunta in criterio.preguntas)

    for pregunta_id in sorted(ids_preguntas - ids_cubiertas):
        errores.append(
            ErrorValidacionSalida(
                codigo="PREGUNTA_NO_CUBIERTA",
                mensaje="La pregunta no esta cubierta por ningun criterio",
                ubicacion=f"pregunta:{pregunta_id}",
            )
        )

    return errores
