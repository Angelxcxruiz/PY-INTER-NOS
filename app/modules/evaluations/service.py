from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora
from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
)
from app.modules.cases.service import ServicioCasos
from app.modules.evaluations.calculadora import CalculadoraRubrica
from app.modules.evaluations.models import (
    Calificacion,
    RetroalimentacionDocente,
    RetroalimentacionPregunta,
)
from app.modules.evaluations.repository import RepositorioEvaluaciones
from app.modules.participations.service import ServicioParticipaciones
from app.modules.sessions.service import ServicioSesiones


class ServicioEvaluaciones:
    def __init__(self, db: Session, reloj: Reloj | None = None) -> None:
        self.db = db
        self.reloj = reloj
        self.repositorio = RepositorioEvaluaciones(db)
        self.participaciones = ServicioParticipaciones(db, reloj)
        self.sesiones = ServicioSesiones(db, reloj)
        self.casos = ServicioCasos(db, reloj)

    def momento(self):
        return ahora(self.reloj)

    def _obtener_datos_caso(self, sesion_modelo):
        return self.casos.obtener_para_participacion(sesion_modelo.caso_id)

    def _ordenar_preguntas(self, caso):
        return [pregunta for escenario in caso.escenarios for pregunta in escenario.preguntas]

    def calificar_participacion(
        self,
        participacion_id: str,
        commit: bool = True,
    ) -> Calificacion:
        existente = self.repositorio.por_participacion(participacion_id)
        if existente is not None:
            return existente

        participacion = self.participaciones.obtener_modelo(participacion_id)
        if participacion.estado == "EN_PROGRESO":
            raise ErrorConflicto(
                "No se puede calificar una participacion que sigue abierta",
            )

        convocatoria = self.sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        sesion_modelo = self.sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
        caso = self._obtener_datos_caso(sesion_modelo)
        if caso.rubrica is None:
            raise ErrorNoEncontrado("El caso no tiene rubrica")

        respuestas = self.participaciones.obtener_respuestas(participacion_id)
        respuestas_por_pregunta = {
            respuesta.pregunta_id: respuesta.opcion_id for respuesta in respuestas
        }
        resultado = CalculadoraRubrica.desde_modelos(
            caso.rubrica,
            respuestas_por_pregunta,
        ).calcular()

        puntaje_json = {
            clave: (
                str(valor)
                if isinstance(valor, Decimal)
                else [
                    {
                        detalle_clave: str(detalle_valor)
                        if isinstance(detalle_valor, Decimal)
                        else detalle_valor
                        for detalle_clave, detalle_valor in detalle.items()
                    }
                    for detalle in valor
                ]
                if clave == "puntaje_detalle"
                else valor
            )
            for clave, valor in resultado.items()
        }

        calificacion = Calificacion(
            participacion_id=participacion_id,
            convocatoria_id=None,
            nota_final=resultado["nota_final"],
            puntaje_detalle=puntaje_json,
            es_ausencia=False,
            es_parcial=resultado["es_parcial"],
            calculada_en=self.momento(),
        )
        self.repositorio.agregar(calificacion)
        self.db.flush()
        from app.modules.sessions.events import publicar

        publicar(
            self.db,
            "CALIFICACION_REGISTRADA",
            "calificacion",
            calificacion.id,
            {
                "calificacion_id": calificacion.id,
                "participacion_id": participacion_id,
            },
        )

        mapa_opciones = {}
        preguntas = self._ordenar_preguntas(caso)
        for pregunta in preguntas:
            opcion_elegida_id = respuestas_por_pregunta.get(pregunta.id)
            opcion_correcta = next(opcion for opcion in pregunta.opciones if opcion.es_correcta)
            acertada = opcion_elegida_id == opcion_correcta.id
            if opcion_elegida_id is not None:
                opcion_elegida = next(
                    opcion for opcion in pregunta.opciones if opcion.id == opcion_elegida_id
                )
                justificacion = opcion_elegida.justificacion
                mapa_opciones[pregunta.id] = opcion_elegida_id
            else:
                justificacion = opcion_correcta.justificacion
            retroalimentacion = RetroalimentacionPregunta(
                calificacion_id=calificacion.id,
                pregunta_id=pregunta.id,
                opcion_elegida_id=opcion_elegida_id,
                es_correcta=acertada,
                justificacion=justificacion,
            )
            self.repositorio.agregar(retroalimentacion)

        if commit:
            self.db.commit()
            self.db.refresh(calificacion)
        return calificacion

    def registrar_ausencias(self, sesion_id: str, commit: bool = True) -> list[Calificacion]:
        modelo = self.sesiones.obtener_sesion_para_participacion(sesion_id)
        caso = self._obtener_datos_caso(modelo)
        convocatorias = self.sesiones.listar_convocatorias_para_participacion(sesion_id)
        creadas = []
        for convocatoria in convocatorias:
            participaciones = self.participaciones.obtener_intentos_finalizados(convocatoria.id)
            if participaciones:
                continue
            existente = self.repositorio.por_convocatoria_ausencia(convocatoria.id)
            if existente is not None:
                continue
            total = sum(1 for escenario in caso.escenarios for pregunta in escenario.preguntas)
            calificacion = Calificacion(
                participacion_id=None,
                convocatoria_id=convocatoria.id,
                nota_final=Decimal("0.00"),
                puntaje_detalle={
                    "porcentaje": "0",
                    "puntaje_detalle": [],
                    "aciertos": 0,
                    "total_preguntas": total,
                    "errores": total,
                    "es_parcial": False,
                },
                es_ausencia=True,
                es_parcial=False,
                calculada_en=self.momento(),
            )
            self.repositorio.agregar(calificacion)
            creadas.append(calificacion)
        if commit:
            self.db.commit()
        return creadas

    def _participacion_visible(self, participacion_id: str, sesion: dict):
        """El estudiante ve solo la suya; el docente, las de sus sesiones; el admin, todas."""
        if sesion.get("rol") == "ESTUDIANTE":
            return self.participaciones.obtener(participacion_id, sesion)
        if sesion.get("rol") not in {"DOCENTE", "ADMINISTRADOR"}:
            raise ErrorPermiso("No puede consultar este resultado")
        participacion = self.participaciones.obtener_modelo(participacion_id)
        convocatoria = self.sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        self.sesiones.obtener(convocatoria.sesion_id, sesion)
        return participacion

    def resultado_participacion(
        self,
        participacion_id: str,
        sesion: dict,
    ) -> dict:
        participacion = self._participacion_visible(participacion_id, sesion)
        if participacion.estado == "EN_PROGRESO":
            raise ErrorConflicto(
                "El resultado se habilita al finalizar la participacion",
                detalles={"estado_actual": participacion.estado},
            )
        calificacion = self.repositorio.por_participacion(participacion_id)
        if calificacion is None:
            calificacion = self.calificar_participacion(participacion_id)

        convocatoria = self.sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        sesion_modelo = self.sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
        caso = self._obtener_datos_caso(sesion_modelo)
        respuestas_por_pregunta = {
            respuesta.pregunta_id: respuesta.opcion_id
            for respuesta in self.participaciones.obtener_respuestas(participacion_id)
        }

        detalles = []
        aciertos = 0
        preguntas = self._ordenar_preguntas(caso)
        for pregunta in preguntas:
            opcion_correcta = next(opcion for opcion in pregunta.opciones if opcion.es_correcta)
            opcion_elegida_id = respuestas_por_pregunta.get(pregunta.id)
            acertada = opcion_elegida_id == opcion_correcta.id
            if acertada:
                aciertos += 1
            if opcion_elegida_id is None:
                justificacion = opcion_correcta.justificacion
            else:
                opcion_elegida = next(
                    opcion for opcion in pregunta.opciones if opcion.id == opcion_elegida_id
                )
                justificacion = opcion_elegida.justificacion
            detalles.append(
                {
                    "pregunta_id": pregunta.id,
                    "enunciado": pregunta.enunciado,
                    "opcion_elegida_id": opcion_elegida_id,
                    "opcion_correcta_id": opcion_correcta.id,
                    "acertada": acertada,
                    "justificacion": justificacion,
                }
            )

        nota_aprobatoria = (
            caso.rubrica.nota_aprobatoria if caso.rubrica is not None else Decimal("0")
        )
        retroalimentacion = self.repositorio.retroalimentacion_por_participacion(participacion_id)
        return {
            "aciertos": aciertos,
            "errores": len(preguntas) - aciertos,
            "total_preguntas": len(preguntas),
            "nota_final": calificacion.nota_final,
            "nota_aprobatoria": nota_aprobatoria,
            "retroalimentacion": retroalimentacion.texto if retroalimentacion else None,
            "es_parcial": calificacion.es_parcial,
            "es_ausencia": calificacion.es_ausencia,
            "preguntas": detalles,
        }

    def resultado_convocatoria(self, convocatoria_id: str, sesion: dict) -> dict:
        convocatoria = self.sesiones.obtener_convocatoria_para_participacion(convocatoria_id)
        if sesion.get("rol") == "ESTUDIANTE" and convocatoria.estudiante_id != sesion["sub"]:
            raise ErrorPermiso("No puede consultar el resultado de otro estudiante")
        if sesion.get("rol") != "ESTUDIANTE":
            self.sesiones.obtener(convocatoria.sesion_id, sesion)

        ausencia = self.repositorio.por_convocatoria_ausencia(convocatoria_id)
        intentos = self.participaciones.obtener_intentos_finalizados(convocatoria_id)
        if ausencia is not None and not intentos:
            sesion_modelo = self.sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
            caso = self._obtener_datos_caso(sesion_modelo)
            total = sum(1 for escenario in caso.escenarios for pregunta in escenario.preguntas)
            retroalimentacion = self.repositorio.retroalimentacion_por_convocatoria(convocatoria_id)
            return {
                "aciertos": 0,
                "errores": total,
                "total_preguntas": total,
                "nota_final": ausencia.nota_final,
                "retroalimentacion": retroalimentacion.texto if retroalimentacion else None,
                "nota_aprobatoria": (
                    caso.rubrica.nota_aprobatoria if caso.rubrica is not None else Decimal("0")
                ),
                "es_parcial": False,
                "es_ausencia": True,
                "preguntas": [],
            }
        if not intentos:
            raise ErrorNoEncontrado("La convocatoria no tiene resultados")
        ultimo = max(
            intentos,
            key=lambda participacion: participacion.finalizada_en,
        )
        return self.resultado_participacion(ultimo.id, sesion)

    def guardar_retroalimentacion(
        self,
        participacion_id: str | None,
        convocatoria_id: str | None,
        texto: str,
        sesion: dict,
    ) -> RetroalimentacionDocente:
        if sesion.get("rol") not in {"DOCENTE", "ADMINISTRADOR"}:
            raise ErrorPermiso("Solo docentes pueden retroalimentar")

        if participacion_id is not None:
            participacion = self.participaciones.obtener_modelo(participacion_id)
            convocatoria = self.sesiones.obtener_convocatoria_para_participacion(
                participacion.convocatoria_id
            )
            sesion_modelo = self.sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
            existente = self.repositorio.retroalimentacion_por_participacion(participacion_id)
            objetivo_convocatoria = None
        else:
            convocatoria = self.sesiones.obtener_convocatoria_para_participacion(convocatoria_id)
            sesion_modelo = self.sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
            existente = self.repositorio.retroalimentacion_por_convocatoria(convocatoria_id)
            objetivo_convocatoria = convocatoria_id

        caso = self._obtener_datos_caso(sesion_modelo)
        puede = (
            sesion.get("rol") == "ADMINISTRADOR"
            or sesion_modelo.docente_id == sesion["sub"]
            or caso.docente_creador_id == sesion["sub"]
        )
        if not puede:
            raise ErrorPermiso("No puede retroalimentar esta sesion")

        momento = self.momento()
        if existente is not None:
            existente.texto = texto
            existente.actualizada_en = momento
        else:
            existente = RetroalimentacionDocente(
                participacion_id=participacion_id,
                convocatoria_id=objetivo_convocatoria,
                docente_id=sesion["sub"],
                texto=texto,
                creada_en=momento,
                actualizada_en=momento,
            )
            self.repositorio.agregar(existente)
        from app.modules.sessions.events import publicar

        payload = {
            "retroalimentacion_id": existente.id,
        }
        if participacion_id is not None:
            payload["participacion_id"] = participacion_id
        else:
            payload["convocatoria_id"] = convocatoria_id
        publicar(
            self.db,
            "RETROALIMENTACION_AGREGADA",
            "retroalimentacion",
            existente.id,
            payload,
        )
        self.db.commit()
        self.db.refresh(existente)
        return existente
