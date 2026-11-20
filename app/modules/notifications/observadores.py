from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import ahora, mostrar_bogota
from app.core.config import obtener_configuracion
from app.core.security import descifrar
from app.modules.auth.models import Usuario
from app.modules.cases.models import Caso
from app.modules.evaluations.models import Calificacion
from app.modules.notifications.adapters import PuertoCorreo
from app.modules.notifications.models import EntregaCorreo, Notificacion
from app.modules.notifications.plantillas import renderizar
from app.modules.participations.models import Participacion
from app.modules.sessions.models import Convocatoria, Sesion


class Observador(Protocol):
    def manejar(self, db: Session, evento) -> None: ...


class ObservadorNotificacionInterna:
    def manejar(self, db: Session, evento) -> None:
        payload = evento.payload
        destinatarios: list[tuple[str, str, str]] = []

        if evento.tipo in {"SESION_INICIADA", "SESION_FINALIZADA"}:
            sesion_id = payload.get("sesion_id")
            sesion = db.get(Sesion, sesion_id)
            if sesion is not None:
                destinatarios = [
                    (
                        convocatoria.estudiante_id,
                        evento.tipo,
                        (
                            "La sesion ha iniciado"
                            if evento.tipo == "SESION_INICIADA"
                            else "La sesion ha finalizado"
                        ),
                    )
                    for convocatoria in db.scalars(
                        select(Convocatoria).where(Convocatoria.sesion_id == sesion_id)
                    ).all()
                ]
        elif evento.tipo == "RETROALIMENTACION_AGREGADA":
            participacion_id = payload.get("participacion_id")
            convocatoria_id = payload.get("convocatoria_id")
            if participacion_id:
                participacion = db.get(Participacion, participacion_id)
                convocatoria_id = (
                    participacion.convocatoria_id if participacion is not None else None
                )
            if convocatoria_id:
                convocatoria = db.get(Convocatoria, convocatoria_id)
                if convocatoria is not None:
                    destinatarios = [
                        (
                            convocatoria.estudiante_id,
                            evento.tipo,
                            "Tu docente agrego retroalimentacion",
                        )
                    ]

        for usuario_id, tipo, mensaje in destinatarios:
            existente = db.scalar(
                select(Notificacion).where(
                    Notificacion.usuario_id == usuario_id,
                    Notificacion.evento_id == evento.id,
                    Notificacion.tipo == tipo,
                )
            )
            if existente is not None:
                continue
            db.add(
                Notificacion(
                    usuario_id=usuario_id,
                    tipo=tipo,
                    titulo="Inter Nos",
                    mensaje=mensaje,
                    evento_id=evento.id,
                    creada_en=ahora(),
                )
            )


class ObservadorCorreo:
    def __init__(self, puerto: PuertoCorreo) -> None:
        self.puerto = puerto

    def _entrega(
        self,
        db: Session,
        evento,
        destinatario: str,
    ) -> EntregaCorreo:
        existente = db.scalar(
            select(EntregaCorreo).where(
                EntregaCorreo.evento_id == evento.id,
                EntregaCorreo.destinatario == destinatario,
                EntregaCorreo.tipo == evento.tipo,
            )
        )
        if existente is not None:
            return existente
        entrega = EntregaCorreo(
            evento_id=evento.id,
            destinatario=destinatario,
            tipo=evento.tipo,
            estado="PENDIENTE",
            intentos=0,
            creada_en=ahora(),
        )
        db.add(entrega)
        db.flush()
        return entrega

    def manejar(self, db: Session, evento) -> None:
        if evento.tipo == "CONVOCATORIA_CREADA":
            self._manejar_invitacion(db, evento)
        elif evento.tipo == "CALIFICACION_REGISTRADA":
            self._manejar_calificacion(db, evento)
        elif evento.tipo == "SESION_REPROGRAMADA":
            self._manejar_reprogramacion(db, evento)

    def _manejar_invitacion(self, db: Session, evento) -> None:
        convocatoria_id = evento.payload.get("convocatoria_id")
        convocatoria = db.get(Convocatoria, convocatoria_id)
        if convocatoria is None:
            raise RuntimeError("Convocatoria no encontrada")
        sesion = db.get(Sesion, convocatoria.sesion_id)
        estudiante = db.get(Usuario, convocatoria.estudiante_id)
        caso = db.get(Caso, sesion.caso_id) if sesion is not None else None
        if estudiante is None or sesion is None or caso is None:
            raise RuntimeError("Datos de invitacion incompletos")

        entrega = self._entrega(db, evento, estudiante.correo)
        if not convocatoria.codigo_vigente:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = "OMITIDO: convocatoria revocada"
            return
        if sesion.estado == "FINALIZADO":
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = "OMITIDO: sesion finalizada"
            return

        codigo = descifrar(convocatoria.codigo_cifrado)
        datos = {
            "estudiante_nombre": estudiante.nombre,
            "caso_nombre": caso.nombre,
            "mensaje_personalizado": sesion.mensaje_personalizado,
            "inicio": mostrar_bogota(sesion.inicio_programado),
            "fin": mostrar_bogota(sesion.fin_programado),
            "lugar_fisico": sesion.lugar_fisico,
            "tiempo_maximo_min": sesion.tiempo_maximo_min,
            "codigo": codigo,
            "frontend_url": obtener_configuracion().frontend_url,
        }
        html, texto = renderizar(
            "invitacion.html",
            "invitacion.txt",
            datos,
        )
        entrega.intentos += 1
        try:
            self.puerto.enviar(
                estudiante.correo,
                f"Invitacion: {caso.nombre}",
                html,
                texto,
            )
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

    def _manejar_calificacion(self, db: Session, evento) -> None:
        participacion_id = evento.payload.get("participacion_id")
        participacion = db.get(Participacion, participacion_id)
        if participacion is None:
            raise RuntimeError("Participacion no encontrada")
        convocatoria = db.get(Convocatoria, participacion.convocatoria_id)
        estudiante = db.get(Usuario, convocatoria.estudiante_id) if convocatoria else None
        calificacion = db.get(Calificacion, evento.payload.get("calificacion_id"))
        if estudiante is None or calificacion is None:
            raise RuntimeError("Datos de calificacion incompletos")
        entrega = self._entrega(db, evento, estudiante.correo)
        aviso = (
            "La participacion fue parcial"
            if calificacion.es_parcial
            else "Participacion registrada"
        )
        if calificacion.es_ausencia:
            aviso = "Se registro una ausencia"
        html, texto = renderizar(
            "calificacion.html",
            "calificacion.txt",
            {"nota_final": calificacion.nota_final, "aviso": aviso},
        )
        entrega.intentos += 1
        try:
            self.puerto.enviar(
                estudiante.correo,
                "Calificacion registrada",
                html,
                texto,
            )
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

    def _manejar_reprogramacion(self, db: Session, evento) -> None:
        sesion = db.get(Sesion, evento.payload.get("sesion_id"))
        if sesion is None:
            raise RuntimeError("Sesion no encontrada")
        convocatorias = db.scalars(
            select(Convocatoria).where(
                Convocatoria.sesion_id == sesion.id,
                Convocatoria.codigo_vigente.is_(True),
            )
        ).all()
        for convocatoria in convocatorias:
            estudiante = db.get(Usuario, convocatoria.estudiante_id)
            if estudiante is None:
                continue
            entrega = self._entrega(db, evento, estudiante.correo)
            html, texto = renderizar(
                "reprogramacion.html",
                "reprogramacion.txt",
                {
                    "inicio": mostrar_bogota(sesion.inicio_programado),
                    "fin": mostrar_bogota(sesion.fin_programado),
                },
            )
            entrega.intentos += 1
            try:
                self.puerto.enviar(
                    estudiante.correo,
                    "Sesion reprogramada",
                    html,
                    texto,
                )
            except Exception as exc:
                entrega.estado = "FALLIDO"
                entrega.ultimo_error = str(exc)
                raise
            entrega.estado = "ENVIADO"
            entrega.ultimo_error = None
            entrega.enviado_en = ahora()
