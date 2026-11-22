from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora
from app.core.config import obtener_configuracion
from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.core.security import (
    cifrar,
    descifrar,
    generar_codigo,
    hash_codigo,
)
from app.modules.auth.models import Usuario
from app.modules.auth.service import ServicioUsuarios
from app.modules.cases.service import ServicioCasos
from app.modules.sessions.events import publicar
from app.modules.sessions.models import (
    Convocatoria,
    EspacioAcademico,
    Sesion,
)
from app.modules.sessions.repository import RepositorioSesiones
from app.modules.sessions.schemas import (
    ConvocadoEntrada,
    DatosEspacioAcademico,
    SesionEditarEntrada,
    SesionEntrada,
)


class ServicioSesiones:
    def __init__(self, db: Session, reloj: Reloj | None = None) -> None:
        self.db = db
        self.repositorio = RepositorioSesiones(db)
        self.reloj = reloj
        self.caso_servicio = ServicioCasos(db, reloj)
        self.configuracion = obtener_configuracion()

    def momento(self):
        return ahora(self.reloj)

    def _puede_todo(self, sesion: dict) -> bool:
        return sesion.get("rol") == "ADMINISTRADOR"

    def _verificar_propietario_sesion(self, sesion_modelo: Sesion, sesion: dict) -> None:
        if not self._puede_todo(sesion) and sesion_modelo.docente_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente dueño puede gestionar esta sesion")

    def _obtener_sesion(self, sesion_id: str) -> Sesion:
        sesion = self.repositorio.sesion_por_id(sesion_id)
        if sesion is None:
            raise ErrorNoEncontrado("Sesion no encontrada")
        return sesion

    def listar(
        self,
        sesion: dict,
        estado: str | None,
        limite: int,
        desplazamiento: int,
    ) -> list[Sesion]:
        docente_id = None if self._puede_todo(sesion) else sesion["sub"]
        return self.repositorio.listar_sesiones(
            docente_id,
            estado,
            limite,
            desplazamiento,
        )

    def obtener(self, sesion_id: str, sesion: dict) -> Sesion:
        modelo = self._obtener_sesion(sesion_id)
        self._verificar_propietario_sesion(modelo, sesion)
        return modelo

    def obtener_sesion_para_participacion(self, sesion_id: str) -> Sesion:
        return self._obtener_sesion(sesion_id)

    def obtener_convocatoria_para_participacion(self, convocatoria_id: str):
        convocatoria = self.repositorio.convocatoria_por_id(convocatoria_id)
        if convocatoria is None:
            raise ErrorNoEncontrado("Convocatoria no encontrada")
        return convocatoria

    def listar_convocatorias_para_participacion(self, sesion_id: str):
        return self.repositorio.convocatorias_sesion(sesion_id)

    def listar_espacios(self, sesion: dict) -> list[EspacioAcademico]:
        from sqlalchemy import select

        stmt = select(EspacioAcademico).order_by(EspacioAcademico.nombre)
        if not self._puede_todo(sesion):
            stmt = stmt.where(EspacioAcademico.docente_id == sesion["sub"])
        return list(self.db.scalars(stmt).all())

    def crear_espacio(
        self,
        sesion: dict,
        nombre: str,
        codigo: str | None,
    ) -> EspacioAcademico:
        existente = self.repositorio.espacio_por_nombre(sesion["sub"], nombre)
        if existente is not None:
            if codigo is not None:
                existente.codigo = codigo
            self.db.commit()
            self.db.refresh(existente)
            return existente
        entidad = EspacioAcademico(
            nombre=nombre,
            codigo=codigo,
            docente_id=sesion["sub"],
            creado_en=self.momento(),
        )
        self.repositorio.agregar(entidad)
        self.db.commit()
        self.db.refresh(entidad)
        return entidad

    def _obtener_espacio(
        self,
        sesion: dict,
        espacio_academico_id: str | None,
        datos: DatosEspacioAcademico | None,
    ) -> EspacioAcademico:
        if espacio_academico_id is not None:
            espacio = self.repositorio.espacio_por_id(espacio_academico_id)
            if espacio is None:
                raise ErrorNoEncontrado("Espacio academico no encontrado")
            if not self._puede_todo(sesion) and espacio.docente_id != sesion["sub"]:
                raise ErrorPermiso("El espacio academico no pertenece al docente")
            return espacio
        if datos is None:
            raise ErrorValidacion("Debe indicar un espacio academico")
        existente = self.repositorio.espacio_por_nombre(sesion["sub"], datos.nombre)
        if existente is not None:
            return existente
        return self.crear_espacio(sesion, datos.nombre, datos.codigo)

    def crear(self, sesion: dict, solicitud: SesionEntrada) -> Sesion:
        caso = self.caso_servicio.obtener(solicitud.caso_id, sesion)
        if caso.estado != "PUBLICADO":
            raise ErrorValidacion(
                "El caso no esta publicado",
                detalles={"estado_actual": caso.estado},
            )
        if not self._puede_todo(sesion) and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente creador puede agendar este caso")

        momento = self.momento()
        if solicitud.inicio_programado <= momento:
            raise ErrorValidacion(
                "El inicio programado debe estar en el futuro",
            )
        if solicitud.fin_programado <= solicitud.inicio_programado:
            raise ErrorValidacion(
                "El fin programado debe ser posterior al inicio",
            )
        if solicitud.tiempo_maximo_min > caso.tiempo_estimado_min:
            raise ErrorValidacion(
                "El tiempo maximo supera el tiempo estimado del caso",
                detalles={
                    "tiempo_maximo_min": solicitud.tiempo_maximo_min,
                    "tiempo_estimado_caso": caso.tiempo_estimado_min,
                },
            )

        espacio = self._obtener_espacio(
            sesion,
            solicitud.espacio_academico_id,
            solicitud.espacio_academico,
        )
        modelo = Sesion(
            caso_id=caso.id,
            docente_id=sesion["sub"],
            espacio_academico_id=espacio.id,
            inicio_programado=solicitud.inicio_programado,
            fin_programado=solicitud.fin_programado,
            tiempo_maximo_min=solicitud.tiempo_maximo_min,
            lugar_fisico=solicitud.lugar_fisico,
            mensaje_personalizado=solicitud.mensaje_personalizado,
            estado="SIN_INICIAR",
            creada_en=momento,
        )
        self.repositorio.agregar(modelo)
        self.db.flush()

        for convocado in solicitud.convocados:
            self.agregar_convocado(modelo, convocado, sesion, confirmar=False)

        self.db.commit()
        self.db.refresh(modelo)
        return modelo

    def agregar_convocado(
        self,
        modelo: Sesion,
        convocado: ConvocadoEntrada,
        sesion: dict,
        confirmar: bool = True,
    ) -> Convocatoria:
        self._verificar_propietario_sesion(modelo, sesion)
        if modelo.estado == "FINALIZADO":
            raise ErrorConflicto("No se puede convocar estudiantes en una sesion finalizada")

        correo = convocado.correo.strip().lower()
        usuario = self.repositorio.usuario_por_correo(correo)
        if usuario is None:
            usuario = Usuario(
                nombre=convocado.nombre,
                correo=correo,
                hash_contrasena=None,
                rol="ESTUDIANTE",
                activo=True,
                creado_en=self.momento(),
                actualizado_en=self.momento(),
            )
            self.repositorio.agregar(usuario)
        elif usuario.rol != "ESTUDIANTE":
            raise ErrorValidacion(
                "El correo pertenece a un usuario que no es estudiante",
            )

        existente = self.repositorio.convocatoria_por_usuario(modelo.id, usuario.id)
        if existente is not None:
            raise ErrorConflicto(
                "El estudiante ya esta convocado en esta sesion",
            )

        # Estudiante nuevo, o existente sin verificar: M1 decide si corresponde enviar el enlace
        # (no lo hace si ya está verificado ni si se pidió uno hace pocos minutos).
        ServicioUsuarios(self.db, self.reloj).solicitar_verificacion_correo(usuario)

        codigo = generar_codigo(8)
        convocatoria = Convocatoria(
            sesion_id=modelo.id,
            estudiante_id=usuario.id,
            codigo_cifrado=cifrar(codigo),
            codigo_hash=hash_codigo(codigo),
            codigo_vigente=True,
            creada_en=self.momento(),
        )
        self.repositorio.agregar(convocatoria)
        publicar(
            self.db,
            "CONVOCATORIA_CREADA",
            "convocatoria",
            convocatoria.id,
            {"convocatoria_id": convocatoria.id, "sesion_id": modelo.id},
        )
        if confirmar:
            self.db.commit()
            self.db.refresh(convocatoria)
        return convocatoria

    def agregar_convocados(
        self,
        sesion_id: str,
        convocados: list[ConvocadoEntrada],
        sesion: dict,
    ) -> list[Convocatoria]:
        modelo = self._obtener_sesion(sesion_id)
        creadas = [self.agregar_convocado(modelo, convocado, sesion) for convocado in convocados]
        return creadas

    def listar_convocatorias(self, sesion_id: str, sesion: dict) -> list[Convocatoria]:
        modelo = self._obtener_sesion(sesion_id)
        self._verificar_propietario_sesion(modelo, sesion)
        return self.repositorio.convocatorias_sesion(modelo.id)

    def retirar_convocado(
        self,
        sesion_id: str,
        convocatoria_id: str,
        sesion: dict,
    ) -> None:
        modelo = self._obtener_sesion(sesion_id)
        self._verificar_propietario_sesion(modelo, sesion)
        if modelo.estado == "FINALIZADO":
            raise ErrorConflicto("No se puede retirar convocados de una sesion finalizada")
        convocatoria = self.repositorio.convocatoria_por_id(convocatoria_id)
        if convocatoria is None or convocatoria.sesion_id != modelo.id:
            raise ErrorNoEncontrado("Convocatoria no encontrada")
        convocatoria.codigo_vigente = False
        convocatoria.revocada_en = self.momento()
        publicar(
            self.db,
            "CONVOCATORIA_REVOCADA",
            "convocatoria",
            convocatoria.id,
            {"convocatoria_id": convocatoria.id, "sesion_id": modelo.id},
        )
        self.db.commit()

    def ver_codigo(
        self,
        sesion_id: str,
        convocatoria_id: str,
        sesion: dict,
    ) -> str:
        modelo = self._obtener_sesion(sesion_id)
        self._verificar_propietario_sesion(modelo, sesion)
        convocatoria = self.repositorio.convocatoria_por_id(convocatoria_id)
        if convocatoria is None or convocatoria.sesion_id != modelo.id:
            raise ErrorNoEncontrado("Convocatoria no encontrada")
        if convocatoria.codigo_cifrado is None:
            raise ErrorNoEncontrado("La convocatoria no tiene un codigo vigente")
        return descifrar(convocatoria.codigo_cifrado)

    def regenerar_codigo(
        self,
        sesion_id: str,
        convocatoria_id: str,
        sesion: dict,
    ) -> str:
        modelo = self._obtener_sesion(sesion_id)
        self._verificar_propietario_sesion(modelo, sesion)
        convocatoria = self.repositorio.convocatoria_por_id(convocatoria_id)
        if convocatoria is None or convocatoria.sesion_id != modelo.id:
            raise ErrorNoEncontrado("Convocatoria no encontrada")
        codigo = generar_codigo(8)
        convocatoria.codigo_cifrado = cifrar(codigo)
        convocatoria.codigo_hash = hash_codigo(codigo)
        convocatoria.codigo_vigente = True
        convocatoria.revocada_en = None
        publicar(
            self.db,
            "CODIGO_REGENERADO",
            "convocatoria",
            convocatoria.id,
            {"convocatoria_id": convocatoria.id, "sesion_id": modelo.id},
        )
        self.db.commit()
        return codigo

    def reprogramar(
        self,
        sesion_id: str,
        solicitud: SesionEditarEntrada,
        sesion: dict,
    ) -> Sesion:
        modelo = self.repositorio.sesion_bloqueada(sesion_id)
        if modelo is None:
            raise ErrorNoEncontrado("Sesion no encontrada")
        self._verificar_propietario_sesion(modelo, sesion)
        if modelo.estado != "SIN_INICIAR":
            raise ErrorConflicto(
                "Solo se puede reprogramar una sesion sin iniciar",
                detalles={"estado_actual": modelo.estado},
            )
        inicio = solicitud.inicio_programado or modelo.inicio_programado
        fin = solicitud.fin_programado or modelo.fin_programado
        if fin <= inicio:
            raise ErrorValidacion("El fin programado debe ser posterior al inicio")
        if solicitud.tiempo_maximo_min is not None:
            caso = self.caso_servicio.obtener(modelo.caso_id, sesion)
            if solicitud.tiempo_maximo_min > caso.tiempo_estimado_min:
                raise ErrorValidacion(
                    "El tiempo maximo supera el tiempo estimado del caso",
                    detalles={
                        "tiempo_maximo_min": solicitud.tiempo_maximo_min,
                        "tiempo_estimado_caso": caso.tiempo_estimado_min,
                    },
                )
            modelo.tiempo_maximo_min = solicitud.tiempo_maximo_min
        modelo.inicio_programado = inicio
        modelo.fin_programado = fin
        if solicitud.lugar_fisico is not None:
            modelo.lugar_fisico = solicitud.lugar_fisico
        if solicitud.mensaje_personalizado is not None:
            modelo.mensaje_personalizado = solicitud.mensaje_personalizado
        publicar(
            self.db,
            "SESION_REPROGRAMADA",
            "sesion",
            modelo.id,
            {"sesion_id": modelo.id},
        )
        self.db.commit()
        self.db.refresh(modelo)
        return modelo

    def iniciar(self, sesion_id: str, sesion: dict) -> Sesion:
        modelo = self.repositorio.sesion_bloqueada(sesion_id)
        if modelo is None:
            raise ErrorNoEncontrado("Sesion no encontrada")
        self._verificar_propietario_sesion(modelo, sesion)
        if modelo.estado != "SIN_INICIAR":
            raise ErrorConflicto(
                "La sesion no puede iniciarse desde su estado actual",
                detalles={"estado_actual": modelo.estado},
            )
        modelo.estado = "EN_CURSO"
        modelo.iniciada_en = self.momento()
        publicar(
            self.db,
            "SESION_INICIADA",
            "sesion",
            modelo.id,
            {"sesion_id": modelo.id},
        )
        self.db.commit()
        self.db.refresh(modelo)
        return modelo

    def finalizar(self, sesion_id: str, sesion: dict) -> Sesion:
        modelo = self.repositorio.sesion_bloqueada(sesion_id)
        if modelo is None:
            raise ErrorNoEncontrado("Sesion no encontrada")
        self._verificar_propietario_sesion(modelo, sesion)
        if modelo.estado not in {"SIN_INICIAR", "EN_CURSO"}:
            raise ErrorConflicto(
                "La sesion no puede finalizarse desde su estado actual",
                detalles={"estado_actual": modelo.estado},
            )
        self._finalizar_modelo(modelo, "DOCENTE")
        from app.modules.evaluations.service import ServicioEvaluaciones
        from app.modules.participations.service import ServicioParticipaciones

        cerradas = ServicioParticipaciones(self.db, self.reloj).cerrar_por_sesion(modelo.id)
        evaluaciones = ServicioEvaluaciones(self.db, self.reloj)
        for participacion in cerradas:
            evaluaciones.calificar_participacion(
                participacion.id,
                commit=False,
            )
        evaluaciones.registrar_ausencias(
            modelo.id,
            commit=False,
        )
        publicar(
            self.db,
            "SESION_FINALIZADA",
            "sesion",
            modelo.id,
            {"sesion_id": modelo.id},
        )
        self.db.commit()
        self.db.refresh(modelo)
        return modelo

    def _finalizar_modelo(self, modelo: Sesion, finalizada_por: str) -> None:
        modelo.estado = "FINALIZADO"
        modelo.finalizada_en = self.momento()
        modelo.finalizada_por = finalizada_por

    def cerrar_sesiones_vencidas(self) -> int:
        dias = int(getattr(self.configuracion, "dias_cierre_automatico", 1))
        limite = self.momento() - timedelta(days=dias)
        cerradas = 0
        sesiones = self.repositorio.sesiones_vencidas(limite)
        for modelo in sesiones:
            try:
                limite_sesion = modelo.fin_programado + timedelta(days=dias)
                if limite_sesion >= self.momento():
                    continue
                self._finalizar_modelo(modelo, "SISTEMA")
                from app.modules.evaluations.service import ServicioEvaluaciones
                from app.modules.participations.service import ServicioParticipaciones

                cerradas = ServicioParticipaciones(self.db, self.reloj).cerrar_por_sesion(modelo.id)
                evaluaciones = ServicioEvaluaciones(self.db, self.reloj)
                for participacion in cerradas:
                    evaluaciones.calificar_participacion(
                        participacion.id,
                        commit=False,
                    )
                evaluaciones.registrar_ausencias(
                    modelo.id,
                    commit=False,
                )
                publicar(
                    self.db,
                    "SESION_FINALIZADA",
                    "sesion",
                    modelo.id,
                    {"sesion_id": modelo.id},
                )
                self.db.commit()
                cerradas += 1
            except Exception as exc:
                self.db.rollback()
                import logging

                logging.getLogger(__name__).exception(
                    "Error al cerrar sesion vencida %s: %s",
                    modelo.id,
                    exc,
                )
        return cerradas
