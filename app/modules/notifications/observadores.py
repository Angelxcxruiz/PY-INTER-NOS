from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import ahora, como_utc, mostrar_bogota
from app.core.config import obtener_configuracion
from app.core.security import descifrar
from app.modules.auth.models import TokenCorreo, Usuario
from app.modules.auth.service import ServicioUsuarios
from app.modules.cases.models import Caso
from app.modules.evaluations.models import Calificacion
from app.modules.notifications.adapters import PuertoCorreo
from app.modules.notifications.models import EntregaCorreo, Notificacion
from app.modules.notifications.plantillas import renderizar
from app.modules.participations.models import Participacion
from app.modules.sessions.models import Convocatoria, Sesion

# tipo de evento -> (plantilla, asunto, ruta del frontend, texto de vigencia)
PLANTILLAS_TOKEN = {
    "RESTABLECIMIENTO_CONTRASENA_SOLICITADO": (
        "restablecer_contrasena",
        "Restablece tu contraseña de Inter Nos",
        "/restablecer-contrasena",
        lambda c: f"{c.token_restablecer_expira_min} minutos",
    ),
}


class Observador(Protocol):
    def manejar(self, db: Session, evento) -> None: ...


class ObservadorNotificacionInterna:
    @staticmethod
    def _administradores(db: Session) -> list[str]:
        return list(
            db.scalars(
                select(Usuario.id).where(Usuario.rol == "ADMINISTRADOR", Usuario.activo.is_(True))
            ).all()
        )

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

        elif evento.tipo == "DOCENTE_REGISTRADO":
            docente = db.get(Usuario, payload.get("usuario_id"))
            if docente is not None:
                destinatarios = [
                    (
                        admin_id,
                        evento.tipo,
                        f"Nuevo docente pendiente de aprobación: {docente.nombre}",
                    )
                    for admin_id in self._administradores(db)
                ]
        elif evento.tipo == "REGISTRO_VERIFICADO":
            nuevo = db.get(Usuario, payload.get("usuario_id"))
            if nuevo is not None:
                es_docente = nuevo.rol == "DOCENTE"
                destinatarios = [
                    (
                        nuevo.id,
                        evento.tipo,
                        "Correo verificado: tu cuenta está en revisión por el administrador."
                        if es_docente
                        else "Correo verificado: ¡bienvenido a Inter Nos!",
                    )
                ]
                if es_docente:
                    # Los administradores se enteran solo cuando el correo ya está verificado.
                    destinatarios += [
                        (
                            admin_id,
                            evento.tipo,
                            f"Nuevo docente pendiente de aprobación: {nuevo.nombre}",
                        )
                        for admin_id in self._administradores(db)
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
        elif evento.tipo in PLANTILLAS_TOKEN:
            self._manejar_token(db, evento)
        elif evento.tipo == "VERIFICACION_CORREO_SOLICITADA":
            self._manejar_verificacion(db, evento)
        elif evento.tipo in {"DOCENTE_APROBADO", "DOCENTE_RECHAZADO"}:
            self._manejar_decision_docente(db, evento)
        elif evento.tipo == "REGISTRO_INICIADO":
            self._manejar_registro_iniciado(db, evento)

    def _manejar_registro_iniciado(self, db: Session, evento) -> None:
        entrega_previa = db.scalar(
            select(EntregaCorreo).where(
                EntregaCorreo.evento_id == evento.id,
                EntregaCorreo.tipo == evento.tipo,
            )
        )
        if entrega_previa is not None and entrega_previa.estado == "ENVIADO":
            return

        # El código se genera aquí, justo al construir el correo; en la base queda solo su hash.
        preparado = ServicioUsuarios(db).preparar_codigo_registro(
            evento.payload.get("codigo_registro_id")
        )
        if preparado is None:
            return  # ya reemplazado, usado o cuenta verificada: no hay nada que enviar
        usuario, codigo = preparado

        html, texto = renderizar(
            "codigo_registro.html",
            "codigo_registro.txt",
            {
                "nombre": usuario.nombre,
                "codigo": codigo,
                "vigencia": f"{obtener_configuracion().codigo_registro_expira_min} minutos",
            },
        )
        entrega = self._entrega(db, evento, usuario.correo)
        entrega.intentos += 1
        try:
            self.puerto.enviar(
                usuario.correo, "Tu código de verificación de Inter Nos", html, texto
            )
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

    def _manejar_decision_docente(self, db: Session, evento) -> None:
        usuario = db.get(Usuario, evento.payload.get("usuario_id"))
        # Si el usuario ya no existe no hay a quién avisar: no es un fallo reintentable.
        if usuario is None:
            return
        entrega = self._entrega(db, evento, usuario.correo)
        if entrega.estado == "ENVIADO":
            return

        aprobado = evento.tipo == "DOCENTE_APROBADO"
        plantilla = "docente_aprobado" if aprobado else "docente_rechazado"
        html, texto = renderizar(
            f"{plantilla}.html",
            f"{plantilla}.txt",
            {
                "nombre": usuario.nombre,
                "motivo": usuario.motivo_rechazo,
                "frontend_url": obtener_configuracion().frontend_url,
            },
        )
        asunto = (
            "Tu cuenta de docente en Inter Nos fue aprobada"
            if aprobado
            else "Tu solicitud de cuenta de docente en Inter Nos"
        )
        entrega.intentos += 1
        try:
            self.puerto.enviar(usuario.correo, asunto, html, texto)
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

    def _manejar_verificacion(self, db: Session, evento) -> None:
        entrega_previa = db.scalar(
            select(EntregaCorreo).where(
                EntregaCorreo.evento_id == evento.id,
                EntregaCorreo.tipo == evento.tipo,
            )
        )
        if entrega_previa is not None and entrega_previa.estado == "ENVIADO":
            return

        # El token se genera aquí, justo al construir el correo; en la base queda solo su hash.
        preparado = ServicioUsuarios(db).preparar_token_verificacion(
            evento.payload.get("verificacion_id")
        )
        if preparado is None:
            return
        usuario, token = preparado

        configuracion = obtener_configuracion()
        enlace = f"{configuracion.frontend_url.rstrip('/')}/verificar-correo?token={token}"
        html, texto = renderizar(
            "verificar_correo.html",
            "verificar_correo.txt",
            {
                "nombre": usuario.nombre,
                "enlace": enlace,
                "vigencia": f"{configuracion.verificacion_expira_horas} horas",
            },
        )
        entrega = self._entrega(db, evento, usuario.correo)
        entrega.intentos += 1
        try:
            self.puerto.enviar(usuario.correo, "Verifica tu correo de Inter Nos", html, texto)
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

    def _manejar_token(self, db: Session, evento) -> None:
        plantilla, asunto, ruta, vigencia = PLANTILLAS_TOKEN[evento.tipo]
        token = db.get(TokenCorreo, evento.payload.get("token_id"))
        # Sin token vigente no hay nada que enviar: no es un fallo, el enlace ya no sirve.
        if token is None or token.usado_en is not None or como_utc(token.expira_en) <= ahora():
            return
        usuario = db.get(Usuario, token.usuario_id)
        if usuario is None or not usuario.activo:
            return

        entrega = self._entrega(db, evento, usuario.correo)
        if entrega.estado == "ENVIADO":
            return

        configuracion = obtener_configuracion()
        enlace = (
            f"{configuracion.frontend_url.rstrip('/')}{ruta}?token={descifrar(token.token_cifrado)}"
        )
        html, texto = renderizar(
            f"{plantilla}.html",
            f"{plantilla}.txt",
            {
                "nombre": usuario.nombre,
                "enlace": enlace,
                "vigencia": vigencia(configuracion),
            },
        )
        entrega.intentos += 1
        try:
            self.puerto.enviar(usuario.correo, asunto, html, texto)
        except Exception as exc:
            entrega.estado = "FALLIDO"
            entrega.ultimo_error = str(exc)
            raise
        entrega.estado = "ENVIADO"
        entrega.ultimo_error = None
        entrega.enviado_en = ahora()

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
