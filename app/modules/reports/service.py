from collections import Counter
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import mostrar_bogota
from app.core.exceptions import ErrorNoEncontrado, ErrorPermiso
from app.modules.reports.estadisticas import (
    distribucion_por_rangos,
    resumen_registros,
    tasa,
)
from app.modules.reports.repository import RepositorioReportes


class ServicioReportes:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        self.repositorio = RepositorioReportes(db)

    def _verificar_sesion(self, sesion_id: str, sesion: dict):
        modelo = self.repositorio.sesion_por_id(sesion_id)
        if modelo is None:
            raise ErrorNoEncontrado("Sesion no encontrada")
        if sesion.get("rol") != "ADMINISTRADOR" and modelo.docente_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente dueño puede consultar esta sesion")
        return modelo

    def _traducir_estado(self, participaciones: list, ausencia) -> str:
        if ausencia is not None:
            return "AUSENTE"
        if not participaciones:
            return "NO_INICIO"
        finalizadas = [
            participacion
            for participacion in participaciones
            if participacion.estado
            in {
                "FINALIZADA",
                "EXPIRADA",
                "CERRADA_POR_SESION",
            }
            and participacion.finalizada_en is not None
        ]
        if finalizadas:
            ultima = max(
                finalizadas,
                key=lambda participacion: participacion.finalizada_en,
            )
            if ultima.estado == "EXPIRADA":
                return "EXPIRA"
            if ultima.estado == "CERRADA_POR_SESION":
                return "CERRADA_POR_SESION"
            return "FINALIZO"

        for participacion in participaciones:
            if participacion.estado == "EN_PROGRESO":
                return "EN_PROGRESO"
        return "NO_INICIO"

    def _ultimo_intento_finalizado(self, participaciones: list):
        finalizados = [
            participacion
            for participacion in participaciones
            if participacion.estado
            in {
                "FINALIZADA",
                "EXPIRADA",
                "CERRADA_POR_SESION",
            }
            and participacion.finalizada_en is not None
        ]
        if not finalizados:
            return None
        return max(
            finalizados,
            key=lambda participacion: participacion.finalizada_en,
        )

    def registros_sesion(self, sesion_id: str, sesion: dict) -> list[dict]:
        modelo = self._verificar_sesion(sesion_id, sesion)
        caso = self.repositorio.caso_por_id(modelo.caso_id)
        total_preguntas = (
            sum(1 for escenario in caso.escenarios for pregunta in escenario.preguntas)
            if caso is not None
            else 0
        )
        registros = []

        for convocatoria in self.repositorio.convocatorias_sesion(sesion_id):
            estudiante = self.repositorio.usuario_por_id(convocatoria.estudiante_id)
            participaciones = self.repositorio.participaciones_convocatoria(convocatoria.id)
            ausencia = self.repositorio.calificacion_ausencia(convocatoria.id)
            intento = self._ultimo_intento_finalizado(participaciones)
            estado = self._traducir_estado(participaciones, ausencia)

            respuestas = []
            if intento is not None:
                respuestas = self.repositorio.respuestas_participacion(intento.id)
            calificacion = None
            if intento is not None:
                calificacion = self.repositorio.calificacion_participacion(intento.id)
            if ausencia is not None:
                calificacion = ausencia

            retroalimentacion = ""
            if intento is not None:
                fila_retro = self.repositorio.retroalimentacion_participacion(intento.id)
                retroalimentacion = fila_retro.texto if fila_retro is not None else ""
            if ausencia is not None:
                fila_retro = self.repositorio.retroalimentacion_convocatoria(convocatoria.id)
                retroalimentacion = fila_retro.texto if fila_retro is not None else ""

            aciertos = None
            if calificacion is not None:
                detalle = calificacion.puntaje_detalle or {}
                aciertos = detalle.get("aciertos")
            elif intento is not None:
                aciertos = 0

            registros.append(
                {
                    "convocatoria_id": convocatoria.id,
                    "nombre": estudiante.nombre if estudiante is not None else "",
                    "correo": estudiante.correo if estudiante is not None else "",
                    "estado": estado,
                    "iniciada_en": (
                        intento.iniciada_en
                        if intento is not None
                        else (participaciones[0].iniciada_en if participaciones else None)
                    ),
                    "finalizada_en": intento.finalizada_en if intento is not None else None,
                    "respondidas": len(respuestas),
                    "total_preguntas": total_preguntas,
                    "aciertos": aciertos,
                    "nota_final": (
                        Decimal(str(calificacion.nota_final)) if calificacion is not None else None
                    ),
                    "parcial": (calificacion.es_parcial if calificacion is not None else False),
                    "ausente": (calificacion.es_ausencia if calificacion is not None else False),
                    "retroalimentacion": retroalimentacion,
                    "puntaje_detalle": (
                        calificacion.puntaje_detalle if calificacion is not None else {}
                    ),
                }
            )
        return registros

    def seguimiento(self, sesion_id: str, sesion: dict) -> dict:
        registros = self.registros_sesion(sesion_id, sesion)
        estadisticas = resumen_registros(registros)
        notas = [
            Decimal(str(registro["nota_final"]))
            for registro in registros
            if registro["nota_final"] is not None
        ]
        estadisticas.update(
            {
                "preguntas": self.estadisticas_preguntas_sesion(sesion_id),
                "criterios": self.estadisticas_criterios(registros),
                "distribucion_notas": distribucion_por_rangos(
                    notas,
                    Decimal("0"),
                    Decimal("5"),
                ),
            }
        )
        return {
            "convocados": registros,
            "estadisticas": estadisticas,
        }

    def estadisticas_sesion(self, sesion_id: str, sesion: dict) -> dict:
        registros = self.registros_sesion(sesion_id, sesion)
        notas = [
            Decimal(str(registro["nota_final"]))
            for registro in registros
            if registro["nota_final"] is not None
        ]
        modelo = self.repositorio.sesion_por_id(sesion_id)
        caso = self.repositorio.caso_por_id(modelo.caso_id)
        escala_min = (
            Decimal(str(caso.rubrica.escala_min))
            if caso is not None and caso.rubrica is not None
            else Decimal("0")
        )
        escala_max = (
            Decimal(str(caso.rubrica.escala_max))
            if caso is not None and caso.rubrica is not None
            else Decimal("5")
        )
        base = resumen_registros(registros)
        base.update(
            {
                "preguntas": self.estadisticas_preguntas_sesion(sesion_id),
                "criterios": self.estadisticas_criterios(registros),
                "distribucion_notas": distribucion_por_rangos(
                    notas,
                    escala_min,
                    escala_max,
                ),
            }
        )
        return base

    def estadisticas_preguntas(self, registros: list[dict]) -> list[dict]:
        return []

    def estadisticas_preguntas_sesion(self, sesion_id: str) -> list[dict]:
        modelo = self.repositorio.sesion_por_id(sesion_id)
        if modelo is None:
            return []
        caso = self.repositorio.caso_por_id(modelo.caso_id)
        if caso is None:
            return []
        preguntas = [pregunta for escenario in caso.escenarios for pregunta in escenario.preguntas]
        resultados = []
        for pregunta in preguntas:
            respondidas = 0
            aciertos = 0
            distribucion = Counter()
            opcion_correcta = next(
                (opcion for opcion in pregunta.opciones if opcion.es_correcta),
                None,
            )
            for convocatoria in self.repositorio.convocatorias_sesion(sesion_id):
                participaciones = self.repositorio.participaciones_convocatoria(convocatoria.id)
                intento = self._ultimo_intento_finalizado(participaciones)
                if intento is None:
                    continue
                for respuesta in self.repositorio.respuestas_participacion(intento.id):
                    if respuesta.pregunta_id != pregunta.id:
                        continue
                    respondidas += 1
                    distribucion[respuesta.opcion_id] += 1
                    if opcion_correcta is not None and respuesta.opcion_id == opcion_correcta.id:
                        aciertos += 1
            opcion_mas_elegida = distribucion.most_common(1)[0][0] if distribucion else None
            resultados.append(
                {
                    "pregunta_id": pregunta.id,
                    "enunciado": pregunta.enunciado,
                    "respondieron": respondidas,
                    "aciertos": aciertos,
                    "tasa_acierto": tasa(aciertos, respondidas),
                    "opcion_mas_elegida": opcion_mas_elegida,
                    "distribucion_opciones": dict(distribucion),
                }
            )
        return resultados

    def estadisticas_criterios(self, registros: list[dict]) -> list[dict]:
        criterios = {}
        for registro in registros:
            detalle = registro.get("puntaje_detalle") or {}
            for criterio in detalle.get("puntaje_detalle", []):
                nombre = criterio.get("nombre")
                if nombre not in criterios:
                    criterios[nombre] = {
                        "nombre": nombre,
                        "total_preguntas": len(criterio.get("preguntas", [])),
                        "aciertos": 0,
                    }
                criterios[nombre]["aciertos"] += int(criterio.get("aciertos", 0))
        for criterio in criterios.values():
            total = int(criterio["total_preguntas"])
            aciertos = int(criterio["aciertos"])
            criterio["tasa_acierto"] = tasa(aciertos, total)
        return list(criterios.values())

    def estadisticas_caso(self, caso_id: str, sesion: dict) -> dict:
        caso = self.repositorio.caso_por_id(caso_id)
        if caso is None:
            raise ErrorNoEncontrado("Caso no encontrado")
        if sesion.get("rol") != "ADMINISTRADOR" and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente creador puede consultar este caso")
        registros = []
        for modelo in self.repositorio.sesiones_caso(caso_id):
            registros.extend(self.registros_sesion(modelo.id, sesion))
        return resumen_registros(registros)

    def estadisticas_espacio(self, espacio_id: str, sesion: dict) -> dict:
        registros = []
        for modelo in self.repositorio.sesiones_espacio(espacio_id):
            if sesion.get("rol") != "ADMINISTRADOR" and modelo.docente_id != sesion["sub"]:
                raise ErrorPermiso("Solo el docente dueño puede consultar este espacio")
            registros.extend(self.registros_sesion(modelo.id, sesion))
        return resumen_registros(registros)

    def filas_csv_participacion(self, sesion_id: str, sesion: dict) -> list[list]:
        registros = self.registros_sesion(sesion_id, sesion)
        filas = []
        for registro in registros:
            filas.append(
                [
                    registro["nombre"],
                    registro["correo"],
                    registro["estado"],
                    (
                        mostrar_bogota(registro["iniciada_en"])
                        if registro["iniciada_en"] is not None
                        else ""
                    ),
                    (
                        mostrar_bogota(registro["finalizada_en"])
                        if registro["finalizada_en"] is not None
                        else ""
                    ),
                    registro["respondidas"],
                    registro["total_preguntas"],
                    registro["aciertos"],
                    registro["nota_final"],
                    "si" if registro["parcial"] else "no",
                    "si" if registro["ausente"] else "no",
                    registro["retroalimentacion"],
                ]
            )
        return filas

    def filas_csv_respuestas(self, sesion_id: str, sesion: dict) -> list[list]:
        modelo = self._verificar_sesion(sesion_id, sesion)
        caso = self.repositorio.caso_por_id(modelo.caso_id)
        filas = []
        if caso is None:
            return filas
        for convocatoria in self.repositorio.convocatorias_sesion(sesion_id):
            estudiante = self.repositorio.usuario_por_id(convocatoria.estudiante_id)
            participaciones = self.repositorio.participaciones_convocatoria(convocatoria.id)
            intento = self._ultimo_intento_finalizado(participaciones)
            respuestas = (
                self.repositorio.respuestas_participacion(intento.id) if intento is not None else []
            )
            respuestas_por_pregunta = {respuesta.pregunta_id: respuesta for respuesta in respuestas}
            for escenario in caso.escenarios:
                for pregunta in escenario.preguntas:
                    respuesta = respuestas_por_pregunta.get(pregunta.id)
                    opcion_elegida = None
                    opcion_correcta = None
                    for opcion in pregunta.opciones:
                        if respuesta is not None and opcion.id == respuesta.opcion_id:
                            opcion_elegida = opcion
                        if opcion.es_correcta:
                            opcion_correcta = opcion
                    acertada = (
                        opcion_elegida is not None
                        and opcion_correcta is not None
                        and opcion_elegida.id == opcion_correcta.id
                    )
                    filas.append(
                        [
                            estudiante.nombre if estudiante is not None else "",
                            estudiante.correo if estudiante is not None else "",
                            escenario.titulo,
                            pregunta.enunciado,
                            opcion_elegida.texto if opcion_elegida is not None else "",
                            opcion_correcta.texto if opcion_correcta is not None else "",
                            "si" if acertada else "no",
                            (
                                opcion_elegida.justificacion
                                if opcion_elegida is not None
                                else (
                                    opcion_correcta.justificacion
                                    if opcion_correcta is not None
                                    else ""
                                )
                            ),
                        ]
                    )
        return filas
