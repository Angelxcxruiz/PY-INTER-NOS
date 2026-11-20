from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PreguntaCalculada:
    id: str
    opcion_correcta_id: str


@dataclass(frozen=True)
class CriterioCalculado:
    id: str
    nombre: str
    peso: Decimal
    pregunta_ids: tuple[str, ...]


@dataclass(frozen=True)
class RubricaCalculada:
    escala_min: Decimal
    escala_max: Decimal
    nota_aprobatoria: Decimal
    criterios: tuple[CriterioCalculado, ...]


class CalculadoraRubrica:
    def __init__(
        self,
        preguntas: list[PreguntaCalculada],
        respuestas: dict[str, str],
        rubrica: RubricaCalculada,
    ) -> None:
        self.preguntas = preguntas
        self.respuestas = respuestas
        self.rubrica = rubrica

    def calcular(self) -> dict:
        respuesta_cero = {}
        aciertos_por_pregunta = {}
        for pregunta in self.preguntas:
            opcion_elegida = self.respuestas.get(pregunta.id)
            aciertos_por_pregunta[pregunta.id] = opcion_elegida == pregunta.opcion_correcta_id
        if not aciertos_por_pregunta:
            aciertos_por_pregunta = respuesta_cero

        total_preguntas = len(self.preguntas)
        aciertos = sum(1 for valor in aciertos_por_pregunta.values() if valor)
        errores = total_preguntas - aciertos
        porcentaje = Decimal("0")
        puntaje_detalle = []

        for criterio in self.rubrica.criterios:
            ids_cubridos = tuple(
                pregunta_id
                for pregunta_id in criterio.pregunta_ids
                if pregunta_id in aciertos_por_pregunta
            )
            cantidad = len(ids_cubridos)
            aciertos_criterio = sum(
                1 for pregunta_id in ids_cubridos if aciertos_por_pregunta[pregunta_id]
            )
            if cantidad == 0:
                aporte = Decimal("0")
            else:
                aporte = Decimal(aciertos_criterio) / Decimal(cantidad) * criterio.peso
            porcentaje += aporte
            puntaje_detalle.append(
                {
                    "nombre": criterio.nombre,
                    "peso": criterio.peso,
                    "preguntas": list(ids_cubridos),
                    "aciertos": aciertos_criterio,
                    "aporte": aporte,
                }
            )

        porcentaje = porcentaje.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        rango = self.rubrica.escala_max - self.rubrica.escala_min
        nota = self.rubrica.escala_min + (porcentaje / Decimal("100")) * rango
        nota_final = nota.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        es_parcial = any(pregunta.id not in self.respuestas for pregunta in self.preguntas)

        return {
            "nota_final": nota_final,
            "porcentaje": porcentaje,
            "puntaje_detalle": puntaje_detalle,
            "aciertos": aciertos,
            "total_preguntas": total_preguntas,
            "errores": errores,
            "es_parcial": es_parcial,
        }

    @classmethod
    def desde_modelos(cls, rubrica_orm, respuestas: dict[str, str]):
        preguntas = []
        for escenario in rubrica_orm.caso.escenarios:
            for pregunta in escenario.preguntas:
                opcion_correcta = next(
                    (opcion.id for opcion in pregunta.opciones if opcion.es_correcta),
                    "",
                )
                preguntas.append(
                    PreguntaCalculada(
                        id=pregunta.id,
                        opcion_correcta_id=opcion_correcta,
                    )
                )
        criterios = tuple(
            CriterioCalculado(
                id=criterio.id,
                nombre=criterio.nombre,
                peso=Decimal(str(criterio.peso)),
                pregunta_ids=tuple(pregunta.id for pregunta in criterio.preguntas),
            )
            for criterio in rubrica_orm.criterios
        )
        rubrica = RubricaCalculada(
            escala_min=Decimal(str(rubrica_orm.escala_min)),
            escala_max=Decimal(str(rubrica_orm.escala_max)),
            nota_aprobatoria=Decimal(str(rubrica_orm.nota_aprobatoria)),
            criterios=criterios,
        )
        return cls(preguntas, respuestas, rubrica)
