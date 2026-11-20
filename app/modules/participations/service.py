from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora
from app.core.config import obtener_configuracion
from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.modules.cases.service import ServicioCasos
from app.modules.participations.calculos import (
    calcular_limite_ingreso_tardio,
    calcular_vence_en,
    segundos_restantes,
)
from app.modules.participations.models import (
    AutorizacionRepeticion,
    Participacion,
    Respuesta,
)
from app.modules.participations.repository import RepositorioParticipaciones
from app.modules.sessions.service import ServicioSesiones


class ServicioParticipaciones:
    def __init__(self, db: Session, reloj: Reloj | None = None) -> None:
        self.db = db
        self.repositorio = RepositorioParticipaciones(db)
        self.reloj = reloj
        self.servicio_sesiones = ServicioSesiones(db, reloj)
        self.servicio_casos = ServicioCasos(db, reloj)
        self.configuracion = obtener_configuracion()

    def momento(self):
        return ahora(self.reloj)

    def obtener_modelo(self, participacion_id: str) -> Participacion:
        participacion = self.repositorio.por_id(participacion_id)
        if participacion is None:
            raise ErrorNoEncontrado("Participacion no encontrada")
        return participacion

    def _verificar_estudiante_convocatoria(self, convocatoria, sesion: dict) -> None:
        if sesion.get("rol") != "ESTUDIANTE":
            raise ErrorPermiso("Solo estudiantes pueden usar participaciones")
        if convocatoria.estudiante_id != sesion["sub"]:
            raise ErrorPermiso("La convocatoria pertenece a otro estudiante")

    def _progreso(self, participacion: Participacion) -> dict:
        respuestas = self.repositorio.respuestas(participacion.id)
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        sesion = self.servicio_sesiones.obtener_sesion_para_participacion(convocatoria.sesion_id)
        caso = self.servicio_casos.obtener_para_participacion(sesion.caso_id)
        total = sum(1 for escenario in caso.escenarios for pregunta in escenario.preguntas)
        if total == 0:
            return {
                "respondidas": 0,
                "total": 0,
                "porcentaje": 0,
                "segundos_restantes": segundos_restantes(participacion.vence_en, self.momento()),
            }
        respondidas = len(respuestas)
        porcentaje = (Decimal(respondidas * 100) / Decimal(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return {
            "respondidas": respondidas,
            "total": sum(1 for escenario in caso.escenarios for pregunta in escenario.preguntas),
            "porcentaje": porcentaje,
            "segundos_restantes": segundos_restantes(participacion.vence_en, self.momento()),
        }

    def iniciar(self, convocatoria_id: str, sesion: dict) -> Participacion:
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            convocatoria_id
        )
        self._verificar_estudiante_convocatoria(convocatoria, sesion)
        if not convocatoria.codigo_vigente:
            raise ErrorConflicto("La convocatoria fue revocada")

        sesion_modelo = self.servicio_sesiones.obtener_sesion_para_participacion(
            convocatoria.sesion_id
        )
        if sesion_modelo.estado == "FINALIZADO":
            raise ErrorConflicto("Nunca se participa en una sesion finalizada")
        if sesion_modelo.estado != "EN_CURSO":
            raise ErrorConflicto("La sesion aun no ha sido iniciada")

        momento = self.momento()
        limite = calcular_limite_ingreso_tardio(
            sesion_modelo.iniciada_en,
            sesion_modelo.tiempo_maximo_min,
            self.configuracion.fraccion_ingreso_tardio,
        )
        if momento > limite:
            raise ErrorValidacion(
                "Se supero el limite de ingreso tardio",
                detalles={
                    "limite_ingreso": limite.isoformat(),
                },
            )

        vigente = self.repositorio.en_progreso_convocatoria(convocatoria_id)
        if vigente is not None:
            if vigente.vence_en <= momento:
                return self._expirar_participacion(vigente, momento)
            return vigente

        intentos = self.repositorio.vigentes_convocatoria(convocatoria_id)
        if intentos:
            autorizacion = self.repositorio.autorizacion_no_usada(convocatoria_id)
            if autorizacion is None:
                raise ErrorConflicto("Ya existe un intento y no hay autorizacion de repeticion")
            autorizacion.usada_en = momento
            numero_intento = max(intento.numero_intento for intento in intentos) + 1
        else:
            numero_intento = 1

        vence_en = calcular_vence_en(
            momento,
            sesion_modelo.tiempo_maximo_min,
            sesion_modelo.fin_programado,
        )
        participacion = Participacion(
            convocatoria_id=convocatoria_id,
            numero_intento=numero_intento,
            iniciada_en=momento,
            vence_en=vence_en,
            estado="EN_PROGRESO",
        )
        self.repositorio.agregar(participacion)
        self.db.commit()
        self.db.refresh(participacion)
        return participacion

    def por_convocatoria(self, convocatoria_id: str, sesion: dict) -> Participacion:
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            convocatoria_id
        )
        self._verificar_estudiante_convocatoria(convocatoria, sesion)
        participacion = self.repositorio.en_progreso_convocatoria(convocatoria_id)
        if participacion is None:
            raise ErrorNoEncontrado("No existe una participacion vigente")
        return participacion

    def obtener(self, participacion_id: str, sesion: dict) -> Participacion:
        participacion = self.repositorio.por_id(participacion_id)
        if participacion is None:
            raise ErrorNoEncontrado("Participacion no encontrada")
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        self._verificar_estudiante_convocatoria(convocatoria, sesion)
        return participacion

    def obtener_respuestas(self, participacion_id: str) -> list[Respuesta]:
        return self.repositorio.respuestas(participacion_id)

    def obtener_intentos_finalizados(self, convocatoria_id: str) -> list[Participacion]:
        return [
            participacion
            for participacion in self.repositorio.vigentes_convocatoria(convocatoria_id)
            if participacion.estado in {"FINALIZADA", "EXPIRADA", "CERRADA_POR_SESION"}
            and participacion.finalizada_en is not None
        ]

    def listar_intentos_modelo(self, convocatoria_id: str) -> list[Participacion]:
        return self.repositorio.vigentes_convocatoria(convocatoria_id)

    def obtener_detalle(self, participacion_id: str, sesion: dict) -> dict:
        participacion = self.obtener(participacion_id, sesion)
        respuestas = self.repositorio.respuestas(participacion.id)
        return {
            "id": participacion.id,
            "convocatoria_id": participacion.convocatoria_id,
            "numero_intento": participacion.numero_intento,
            "iniciada_en": participacion.iniciada_en,
            "vence_en": participacion.vence_en,
            "finalizada_en": participacion.finalizada_en,
            "estado": participacion.estado,
            "motivo_cierre": participacion.motivo_cierre,
            "progreso": self._progreso(participacion),
            "respuestas_actuales": [
                {
                    "pregunta_id": respuesta.pregunta_id,
                    "opcion_id": respuesta.opcion_id,
                    "respondida_en": respuesta.respondida_en,
                    "actualizada_en": respuesta.actualizada_en,
                }
                for respuesta in respuestas
            ],
        }

    def responder(
        self,
        participacion_id: str,
        pregunta_id: str,
        opcion_id: str,
        sesion: dict,
    ) -> dict:
        participacion = self.repositorio.por_id(participacion_id)
        if participacion is None:
            raise ErrorNoEncontrado("Participacion no encontrada")
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        self._verificar_estudiante_convocatoria(convocatoria, sesion)

        momento = self.momento()
        if participacion.estado != "EN_PROGRESO":
            raise ErrorConflicto("La participacion ya esta cerrada")
        if momento > participacion.vence_en:
            return self._expirar_participacion(participacion, momento)

        sesion_modelo = self.servicio_sesiones.obtener_sesion_para_participacion(
            convocatoria.sesion_id
        )
        caso = self.servicio_casos.obtener_para_participacion(sesion_modelo.caso_id)

        pregunta = None
        opcion = None
        for escenario in caso.escenarios:
            for candidata in escenario.preguntas:
                if candidata.id == pregunta_id:
                    pregunta = candidata
                    break
            if pregunta is not None:
                break
        if pregunta is None:
            raise ErrorNoEncontrado("Pregunta no encontrada")
        for candidata in pregunta.opciones:
            if candidata.id == opcion_id:
                opcion = candidata
                break
        if opcion is None or opcion.pregunta_id != pregunta_id:
            raise ErrorNoEncontrado("La opcion no pertenece a la pregunta")

        respuesta = self.repositorio.respuesta(participacion.id, pregunta_id)
        if respuesta is None:
            respuesta = Respuesta(
                participacion_id=participacion.id,
                pregunta_id=pregunta_id,
                opcion_id=opcion_id,
                respondida_en=momento,
                actualizada_en=momento,
            )
            self.repositorio.agregar(respuesta)
        else:
            respuesta.opcion_id = opcion_id
            respuesta.actualizada_en = momento
        self.db.commit()
        progreso = self._progreso(participacion)
        return progreso

    def finalizar(self, participacion_id: str, sesion: dict) -> dict:
        participacion = self.repositorio.por_id_bloqueada(participacion_id)
        if participacion is None:
            raise ErrorNoEncontrado("Participacion no encontrada")
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            participacion.convocatoria_id
        )
        self._verificar_estudiante_convocatoria(convocatoria, sesion)
        if participacion.estado != "EN_PROGRESO":
            raise ErrorConflicto("La participacion ya esta cerrada")

        momento = self.momento()
        if momento > participacion.vence_en:
            resultado = self._expirar_participacion(participacion, momento)
            resultado["estado"] = "EXPIRADA"
            return resultado

        participacion.estado = "FINALIZADA"
        participacion.finalizada_en = momento
        participacion.motivo_cierre = "FINALIZADA_POR_ESTUDIANTE"
        from app.modules.evaluations.service import ServicioEvaluaciones

        ServicioEvaluaciones(self.db, self.reloj).calificar_participacion(
            participacion.id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(participacion)
        resultado = self._progreso(participacion)
        resultado["estado"] = participacion.estado
        return resultado

    def _expirar_participacion(
        self,
        participacion: Participacion,
        momento,
    ) -> dict:
        bloqueada = self.repositorio.por_id_bloqueada(participacion.id)
        if bloqueada is None:
            raise ErrorNoEncontrado("Participacion no encontrada")
        if bloqueada.estado != "EN_PROGRESO":
            return self._progreso(bloqueada)
        bloqueada.estado = "EXPIRADA"
        bloqueada.finalizada_en = momento
        bloqueada.motivo_cierre = "TIEMPO_AGOTADO"
        from app.modules.evaluations.service import ServicioEvaluaciones

        ServicioEvaluaciones(self.db, self.reloj).calificar_participacion(
            bloqueada.id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(bloqueada)
        resultado = self._progreso(bloqueada)
        resultado["estado"] = "EXPIRADA"
        return resultado

    def autorizar_repeticion(
        self,
        convocatoria_id: str,
        motivo: str | None,
        sesion: dict,
    ) -> AutorizacionRepeticion:
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            convocatoria_id
        )
        if sesion.get("rol") not in {"DOCENTE", "ADMINISTRADOR"}:
            raise ErrorPermiso("Solo docentes pueden autorizar repeticiones")
        sesion_modelo = self.servicio_sesiones.obtener_sesion_para_participacion(
            convocatoria.sesion_id
        )
        caso = self.servicio_casos.obtener(sesion_modelo.caso_id, sesion)
        if sesion.get("rol") != "ADMINISTRADOR" and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente creador del caso puede autorizar")

        existente = self.repositorio.autorizacion_no_usada(convocatoria_id)
        if existente is not None:
            raise ErrorConflicto("Ya existe una autorizacion pendiente")
        autorizacion = AutorizacionRepeticion(
            convocatoria_id=convocatoria_id,
            docente_id=sesion["sub"],
            motivo=motivo,
            creada_en=self.momento(),
        )
        self.repositorio.agregar(autorizacion)
        self.db.commit()
        self.db.refresh(autorizacion)
        return autorizacion

    def listar_intentos(self, convocatoria_id: str, sesion: dict) -> list[Participacion]:
        convocatoria = self.servicio_sesiones.obtener_convocatoria_para_participacion(
            convocatoria_id
        )
        sesion_modelo = self.servicio_sesiones.obtener_sesion_para_participacion(
            convocatoria.sesion_id
        )
        if sesion.get("rol") not in {"DOCENTE", "ADMINISTRADOR"}:
            raise ErrorPermiso("Solo docentes pueden listar intentos")
        caso = self.servicio_casos.obtener(sesion_modelo.caso_id, sesion)
        if sesion.get("rol") != "ADMINISTRADOR" and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente creador del caso puede consultar")
        return self.repositorio.vigentes_convocatoria(convocatoria_id)

    def expirar_vencidas(self) -> int:
        momento = self.momento()
        vencidas = self.repositorio.vencidas(momento)
        cerradas = 0
        for participacion in vencidas:
            try:
                participacion.estado = "EXPIRADA"
                participacion.finalizada_en = momento
                participacion.motivo_cierre = "TIEMPO_AGOTADO"
                from app.modules.evaluations.service import ServicioEvaluaciones

                ServicioEvaluaciones(self.db, self.reloj).calificar_participacion(
                    participacion.id,
                    commit=False,
                )
                self.db.commit()
                cerradas += 1
            except Exception:
                self.db.rollback()
        return cerradas

    def cerrar_por_sesion(self, sesion_id: str) -> list[Participacion]:
        convocatorias = self.servicio_sesiones.listar_convocatorias_para_participacion(sesion_id)
        ids = [convocatoria.id for convocatoria in convocatorias]
        abiertas = self.repositorio.abiertas_por_sesion(ids)
        momento = self.momento()
        for participacion in abiertas:
            participacion.estado = "CERRADA_POR_SESION"
            participacion.finalizada_en = momento
            participacion.motivo_cierre = "SESION_FINALIZADA"
        return list(abiertas)
