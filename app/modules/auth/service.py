import hmac
from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora, como_utc
from app.core.config import obtener_configuracion
from app.core.enums import EstadoCuenta, PropositoToken, TipoEvento
from app.core.exceptions import (
    ErrorAutenticacion,
    ErrorConflicto,
    ErrorDominio,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.core.security import (
    cifrar,
    crear_jwt,
    generar_codigo_numerico,
    generar_token,
    hash_codigo_registro,
    hash_contrasena,
    hash_token,
    verificar_contrasena,
)
from app.modules.auth.models import CodigoRegistro, TokenCorreo, Usuario, VerificacionCorreo
from app.modules.auth.repository import RepositorioUsuarios
from app.modules.sessions.events import publicar


class ValidadorConvocatoria(Protocol):
    def __call__(self, correo: str, codigo: str) -> dict: ...


_intentos_login: dict[str, list[datetime]] = {}
_candado_intentos = Lock()

MENSAJE_REGISTRO_DUPLICADO = "No fue posible completar el registro con ese correo"
MENSAJE_CODIGO_INVALIDO = (
    "El código es incorrecto, venció o ya no es válido. Solicita uno nuevo con «Reenviar código»."
)


class ServicioUsuarios:
    def __init__(
        self,
        db: Session,
        reloj: Reloj | None = None,
        validador_convocatoria: ValidadorConvocatoria | None = None,
    ) -> None:
        self.db = db
        self.repositorio = RepositorioUsuarios(db)
        self.reloj = reloj
        self.validador_convocatoria = validador_convocatoria
        self.configuracion = obtener_configuracion()

    def _momento(self) -> datetime:
        return ahora(self.reloj)

    def _dominio_permitido(self, correo: str) -> bool:
        """Única validación de dominio: login de estudiante, alta por admin y registro.

        Acepta el dominio configurado y sus subdominios: con `edu.co`, valen
        `unihumboldt.edu.co` o `estudiantes.otra.edu.co`, pero no `evil-edu.co`.
        """
        correo_normalizado = correo.strip().lower()
        if "@" not in correo_normalizado:
            return False
        dominio_correo = correo_normalizado.rpartition("@")[2]
        return any(
            dominio_correo == dominio or dominio_correo.endswith("." + dominio)
            for dominio in self.configuracion.dominios_permitidos
        )

    def _aplicar_limite(self, correo: str) -> None:
        momento = self._momento()
        clave = correo.lower()
        with _candado_intentos:
            intentos = _intentos_login.setdefault(clave, [])
            intentos[:] = [
                intento for intento in intentos if (momento - intento).total_seconds() < 300
            ]
            if len(intentos) >= 5:
                raise ErrorAutenticacion(
                    "Demasiados intentos fallidos",
                    detalles={"reintentar_en_segundos": 300},
                )

    def _registrar_fallo(self, correo: str) -> None:
        with _candado_intentos:
            _intentos_login.setdefault(correo.lower(), []).append(self._momento())

    def login(self, correo: str, contrasena: str) -> tuple[str, Usuario]:
        correo = correo.strip().lower()
        self._aplicar_limite(correo)
        usuario = self.repositorio.por_correo(correo)
        # Los estudiantes registrados (Fase 11) tienen contraseña; los que crea M3 al convocar no.
        if (
            usuario is None
            or not usuario.activo
            or usuario.rol not in {"ADMINISTRADOR", "DOCENTE", "ESTUDIANTE"}
            or usuario.hash_contrasena is None
            or not verificar_contrasena(usuario.hash_contrasena, contrasena)
        ):
            self._registrar_fallo(correo)
            raise ErrorAutenticacion("Credenciales invalidas")

        # Se revela solo a quien ya probó conocer la contraseña.
        if usuario.estado_cuenta == EstadoCuenta.SIN_VERIFICAR:
            raise ErrorAutenticacion(
                "Verifica tu correo para continuar: te enviamos un código de 6 dígitos. "
                "Si no lo tienes, solicita uno nuevo.",
                codigo="CORREO_SIN_VERIFICAR",
                detalles={
                    "correo": usuario.correo,
                    "verificar": "/api/v1/auth/registro/verificar",
                    "reenviar": "/api/v1/auth/registro/reenviar",
                },
            )
        if usuario.estado_cuenta == EstadoCuenta.RECHAZADO:
            raise ErrorAutenticacion(
                "Tu solicitud de registro fue rechazada. Comunícate con el administrador.",
                codigo="CUENTA_RECHAZADA",
                detalles={"motivo": usuario.motivo_rechazo},
            )

        # Un docente pendiente puede entrar (para ver su estado) pero sin permisos.
        permisos = (
            self.repositorio.permisos(usuario)
            if usuario.estado_cuenta == EstadoCuenta.ACTIVO
            else []
        )
        token = crear_jwt(
            {
                "sub": usuario.id,
                "rol": usuario.rol,
                "permisos": permisos,
                "estado_cuenta": usuario.estado_cuenta,
            },
        )
        return token, usuario

    def login_estudiante(self, correo: str, codigo: str) -> tuple[str, Usuario | None]:
        correo = correo.strip().lower()
        self._aplicar_limite(correo)
        if not self._dominio_permitido(correo):
            self._registrar_fallo(correo)
            raise ErrorAutenticacion("Correo institucional no permitido")
        if self.validador_convocatoria is None:
            raise ErrorConflicto(
                "El servicio de convocatorias aun no esta disponible",
            )
        try:
            datos = self.validador_convocatoria(
                correo,
                codigo,
            )
            convocatoria_id = datos["convocatoria_id"]
            sesion_id = datos["sesion_id"]
        except Exception as exc:
            self._registrar_fallo(correo)
            if getattr(exc, "mensaje", None):
                raise ErrorAutenticacion(
                    exc.mensaje,
                    detalles=exc.detalles,
                ) from exc
            raise ErrorAutenticacion(
                "Correo o codigo de convocatoria invalido",
            ) from exc

        usuario = self.repositorio.por_correo(correo)
        if usuario is None:
            raise ErrorAutenticacion("Correo o codigo de convocatoria invalido")
        token = crear_jwt(
            {
                "sub": usuario.id,
                "rol": "ESTUDIANTE",
                "permisos": [],
                "convocatoria_id": convocatoria_id,
                "sesion_id": sesion_id,
                "caso_id": datos.get("caso_id"),
            },
        )
        return token, usuario

    def crear_usuario(
        self,
        nombre: str,
        correo: str,
        contrasena: str | None,
        rol: str,
        activo: bool,
    ) -> Usuario:
        correo = correo.strip().lower()
        if rol not in {"ADMINISTRADOR", "DOCENTE", "ESTUDIANTE"}:
            raise ErrorValidacion("Rol no permitido")
        if rol == "ESTUDIANTE" and not self._dominio_permitido(correo):
            raise ErrorValidacion(
                "Correo institucional no permitido",
                detalles={"correo": correo},
            )
        if rol in {"ADMINISTRADOR", "DOCENTE"} and not contrasena:
            raise ErrorValidacion("Los docentes y administradores requieren contrasena")
        if self.repositorio.por_correo(correo) is not None:
            raise ErrorConflicto("Ya existe un usuario con ese correo")

        momento = self._momento()
        usuario = Usuario(
            nombre=nombre,
            correo=correo,
            hash_contrasena=hash_contrasena(contrasena) if contrasena else None,
            rol=rol,
            activo=activo,
            # Los docentes y administradores los da de alta el administrador: no se les pide.
            correo_verificado=rol != "ESTUDIANTE",
            verificado_en=momento if rol != "ESTUDIANTE" else None,
            creado_en=momento,
            actualizado_en=momento,
        )
        usuario = self.repositorio.agregar(usuario)
        if rol == "ESTUDIANTE":
            self.solicitar_verificacion_correo(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def listar_usuarios(
        self, limite: int, desplazamiento: int, estado_cuenta: str | None = None
    ) -> list[Usuario]:
        if estado_cuenta is not None and estado_cuenta not in {e.value for e in EstadoCuenta}:
            raise ErrorValidacion("Estado de cuenta no permitido")
        return self.repositorio.listar(limite, desplazamiento, estado_cuenta)

    # --- Registro con verificación por código y aprobación (Fases 11 y 11b) ----------------

    def registrar(self, nombre: str, correo: str, contrasena: str, rol: str) -> Usuario:
        """Autorregistro: la cuenta nace SIN_VERIFICAR, sin acceso a nada.

        Quedan en la misma transacción el usuario, la fila reservada del código y el evento
        REGISTRO_INICIADO. El código de 6 dígitos se genera al construir el correo, así que ni
        aquí ni en el payload del evento existe en claro.
        """
        correo = correo.strip().lower()
        if rol not in {"ESTUDIANTE", "DOCENTE"}:
            raise ErrorValidacion("Solo se puede registrar un estudiante o un docente")
        if len(contrasena) < 8:
            raise ErrorValidacion("La contrasena debe tener al menos 8 caracteres")
        if rol == "ESTUDIANTE" and not self._dominio_permitido(correo):
            raise ErrorValidacion("Los estudiantes deben registrarse con su correo institucional")
        # Mismo mensaje sin importar el rol del usuario que ya existe.
        if self.repositorio.por_correo(correo) is not None:
            raise ErrorConflicto(MENSAJE_REGISTRO_DUPLICADO)

        momento = self._momento()
        usuario = Usuario(
            nombre=nombre.strip(),
            correo=correo,
            hash_contrasena=hash_contrasena(contrasena),
            rol=rol,
            activo=True,
            estado_cuenta=EstadoCuenta.SIN_VERIFICAR,
            creado_en=momento,
            actualizado_en=momento,
        )
        try:
            self.repositorio.agregar(usuario)
        except IntegrityError as exc:  # dos registros simultáneos con el mismo correo
            self.db.rollback()
            raise ErrorConflicto(MENSAJE_REGISTRO_DUPLICADO) from exc
        self._emitir_codigo_registro(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def _emitir_codigo_registro(self, usuario: Usuario) -> None:
        """Reserva la fila del código y publica el evento, sin commit (transacción en curso)."""
        momento = self._momento()
        self.repositorio.eliminar_codigos_registro(usuario.id)
        fila = self.repositorio.agregar_codigo_registro(
            CodigoRegistro(
                usuario_id=usuario.id,
                codigo_hash=None,
                expira_en=momento
                + timedelta(minutes=self.configuracion.codigo_registro_expira_min),
                intentos=0,
                creada_en=momento,
            )
        )
        publicar(
            self.db,
            TipoEvento.REGISTRO_INICIADO.value,
            "usuario",
            usuario.id,
            {"usuario_id": usuario.id, "codigo_registro_id": fila.id},
        )

    def preparar_codigo_registro(
        self, codigo_registro_id: str | None
    ) -> tuple[Usuario, str] | None:
        """Genera el código al construir el correo; en la base queda solo su hash (sin commit).

        Devuelve None si ya no corresponde enviarlo (reemplazado, usado o cuenta ya verificada).
        """
        if not codigo_registro_id:
            return None
        fila = self.repositorio.codigo_registro_por_id(codigo_registro_id)
        if fila is None or fila.usado_en is not None:
            return None
        usuario = self.repositorio.por_id(fila.usuario_id)
        if usuario is None or usuario.estado_cuenta != EstadoCuenta.SIN_VERIFICAR:
            return None
        codigo = generar_codigo_numerico(6)
        fila.codigo_hash = hash_codigo_registro(usuario.id, codigo)
        # La vigencia cuenta desde que se genera el código que recibe el usuario.
        fila.expira_en = self._momento() + timedelta(
            minutes=self.configuracion.codigo_registro_expira_min
        )
        fila.intentos = 0
        self.db.flush()
        return usuario, codigo

    def verificar_registro(self, correo: str, codigo: str) -> Usuario:
        """Código correcto: la cuenta pasa a ACTIVO (estudiante) o PENDIENTE (docente).

        Todos los fallos devuelven el mismo error: no se revela si el correo existe.
        """
        correo = correo.strip().lower()
        usuario = self.repositorio.por_correo(correo)
        fila = None
        if usuario is not None and usuario.estado_cuenta == EstadoCuenta.SIN_VERIFICAR:
            fila = self.repositorio.ultimo_codigo_registro(usuario.id)
        if usuario is None or fila is None:
            raise ErrorDominio(MENSAJE_CODIGO_INVALIDO, codigo="CODIGO_INVALIDO")

        momento = self._momento()
        agotado = fila.intentos >= self.configuracion.codigo_registro_max_intentos
        if (
            fila.usado_en is not None
            or fila.codigo_hash is None
            or como_utc(fila.expira_en) <= momento
            or agotado
        ):
            raise ErrorDominio(MENSAJE_CODIGO_INVALIDO, codigo="CODIGO_INVALIDO")

        esperado = hash_codigo_registro(usuario.id, codigo)
        if not hmac.compare_digest(esperado, fila.codigo_hash):
            fila.intentos += 1
            self.db.commit()  # el intento fallido debe quedar registrado
            raise ErrorDominio(MENSAJE_CODIGO_INVALIDO, codigo="CODIGO_INVALIDO")

        fila.usado_en = momento
        usuario.estado_cuenta = (
            EstadoCuenta.ACTIVO if usuario.rol == "ESTUDIANTE" else EstadoCuenta.PENDIENTE
        )
        usuario.correo_verificado = True
        usuario.verificado_en = momento
        usuario.actualizado_en = momento
        publicar(
            self.db,
            TipoEvento.REGISTRO_VERIFICADO.value,
            "usuario",
            usuario.id,
            {"usuario_id": usuario.id},
        )
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def reenviar_codigo_registro(self, correo: str) -> bool:
        """True si se emitió un código nuevo. Quien llama responde igual en todos los casos."""
        usuario = self.repositorio.por_correo(correo.strip().lower())
        if usuario is None or usuario.estado_cuenta != EstadoCuenta.SIN_VERIFICAR:
            return False
        ultima = self.repositorio.ultimo_codigo_registro(usuario.id)
        espera = self.configuracion.codigo_registro_cooldown_seg
        if (
            ultima is not None
            and (self._momento() - como_utc(ultima.creada_en)).total_seconds() < espera
        ):
            return False
        self._emitir_codigo_registro(usuario)
        self.db.commit()
        return True

    def listar_solicitudes(self, limite: int, desplazamiento: int) -> list[Usuario]:
        return self.repositorio.solicitudes_docentes(limite, desplazamiento)

    def contar_solicitudes(self) -> int:
        return self.repositorio.contar_solicitudes_docentes()

    def _docente_de_solicitud(self, usuario_id: str) -> Usuario:
        usuario = self.repositorio.por_id(usuario_id)
        if usuario is None or usuario.rol != "DOCENTE":
            raise ErrorNoEncontrado("Solicitud no encontrada")
        return usuario

    def aprobar_solicitud(
        self, usuario_id: str, permisos_codigos: list[str], administrador_id: str
    ) -> Usuario:
        """PENDIENTE -> ACTIVO. Repetirlo no duplica permisos ni vuelve a publicar el evento."""
        usuario = self._docente_de_solicitud(usuario_id)
        if usuario.estado_cuenta == EstadoCuenta.RECHAZADO:
            raise ErrorConflicto("La solicitud ya fue rechazada")

        permisos = []
        for codigo in dict.fromkeys(permisos_codigos):
            permiso = self.repositorio.permiso_por_codigo(codigo)
            if permiso is None:
                raise ErrorNoEncontrado("Permiso no encontrado", detalles={"permiso": codigo})
            permisos.append(permiso)

        momento = self._momento()
        if usuario.estado_cuenta == EstadoCuenta.PENDIENTE:
            usuario.estado_cuenta = EstadoCuenta.ACTIVO
            usuario.aprobado_en = momento
            usuario.aprobado_por_id = administrador_id
            usuario.motivo_rechazo = None
            usuario.actualizado_en = momento
            publicar(
                self.db,
                TipoEvento.DOCENTE_APROBADO.value,
                "usuario",
                usuario.id,
                {"usuario_id": usuario.id},
            )
        for permiso in permisos:
            self.repositorio.asignar_permiso(usuario, permiso, momento)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def rechazar_solicitud(self, usuario_id: str, motivo: str | None) -> Usuario:
        """PENDIENTE -> RECHAZADO. Repetirlo no vuelve a publicar el evento."""
        usuario = self._docente_de_solicitud(usuario_id)
        if usuario.estado_cuenta == EstadoCuenta.ACTIVO:
            raise ErrorConflicto("La cuenta ya fue aprobada")
        if usuario.estado_cuenta == EstadoCuenta.PENDIENTE:
            usuario.estado_cuenta = EstadoCuenta.RECHAZADO
            usuario.motivo_rechazo = (motivo or "").strip() or None
            usuario.actualizado_en = self._momento()
            publicar(
                self.db,
                TipoEvento.DOCENTE_RECHAZADO.value,
                "usuario",
                usuario.id,
                {"usuario_id": usuario.id},
            )
            self.db.commit()
            self.db.refresh(usuario)
        return usuario

    def obtener_usuario(self, usuario_id: str) -> Usuario:
        usuario = self.repositorio.por_id(usuario_id)
        if usuario is None:
            raise ErrorNoEncontrado("Usuario no encontrado")
        return usuario

    def editar_usuario(
        self,
        usuario_id: str,
        nombre: str | None,
        contrasena: str | None,
        rol: str | None,
        activo: bool | None,
    ) -> Usuario:
        usuario = self.obtener_usuario(usuario_id)
        if rol is not None:
            if rol not in {"ADMINISTRADOR", "DOCENTE", "ESTUDIANTE"}:
                raise ErrorValidacion("Rol no permitido")
            if (
                rol in {"ADMINISTRADOR", "DOCENTE"}
                and contrasena is None
                and usuario.hash_contrasena is None
            ):
                raise ErrorValidacion("Los docentes y administradores requieren contrasena")
            usuario.rol = rol
        if nombre is not None:
            usuario.nombre = nombre
        if contrasena is not None:
            usuario.hash_contrasena = hash_contrasena(contrasena)
        if activo is not None:
            usuario.activo = activo
        usuario.actualizado_en = self._momento()
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def activar(self, usuario_id: str) -> Usuario:
        return self.editar_usuario(usuario_id, None, None, None, True)

    def desactivar(self, usuario_id: str) -> Usuario:
        return self.editar_usuario(usuario_id, None, None, None, False)

    def eliminar_usuario(self, usuario_id: str) -> None:
        usuario = self.obtener_usuario(usuario_id)
        self.repositorio.eliminar(usuario)
        self.db.commit()

    def listar_permisos(self):
        return self.repositorio.permisos_entidades()

    def asignar_permiso(self, usuario_id: str, permiso_id: str) -> Usuario:
        usuario = self.obtener_usuario(usuario_id)
        permiso = self.repositorio.permiso_por_id(permiso_id)
        if permiso is None:
            raise ErrorNoEncontrado("Permiso no encontrado")
        self.repositorio.asignar_permiso(usuario, permiso, self._momento())
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def quitar_permiso(self, usuario_id: str, permiso_id: str) -> Usuario:
        usuario = self.obtener_usuario(usuario_id)
        permiso = self.repositorio.permiso_por_id(permiso_id)
        if permiso is None:
            raise ErrorNoEncontrado("Permiso no encontrado")
        self.repositorio.quitar_permiso(usuario, permiso)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def sustituir_permisos(self, usuario_id: str, permisos_ids: list[str]) -> Usuario:
        usuario = self.obtener_usuario(usuario_id)
        permisos = []
        for permiso_id in permisos_ids:
            permiso = self.repositorio.permiso_por_id(permiso_id)
            if permiso is None:
                raise ErrorNoEncontrado(
                    "Permiso no encontrado",
                    detalles={"permiso_id": permiso_id},
                )
            permisos.append(permiso)
        self.repositorio.sustituir_permisos(usuario, permisos, self._momento())
        self.db.commit()
        self.db.refresh(usuario)
        return usuario

    def usuario_actual(self, usuario_id: str) -> Usuario:
        usuario = self.obtener_usuario(usuario_id)
        if not usuario.activo:
            raise ErrorPermiso("Usuario desactivado")
        return usuario

    # --- Enlaces de un solo uso por correo -------------------------------------------------

    def _emitir_token(
        self,
        usuario: Usuario,
        proposito: PropositoToken,
        vigencia: timedelta,
        tipo_evento: TipoEvento,
    ) -> bool:
        """Crea el token y su evento de outbox en la transacción en curso (sin commit).

        Devuelve False si se pidió otro enlace hace menos de TOKEN_COOLDOWN_SEG, para que
        nadie pueda usar el endpoint para inundar de correos a un usuario.
        """
        momento = self._momento()
        pendientes = self.repositorio.tokens_pendientes(usuario.id, proposito.value)
        for pendiente in pendientes:
            reciente = (momento - como_utc(pendiente.creado_en)).total_seconds() < (
                self.configuracion.token_cooldown_seg
            )
            if reciente and como_utc(pendiente.expira_en) > momento:
                return False

        # Un enlace nuevo invalida los anteriores sin usar.
        for pendiente in pendientes:
            pendiente.usado_en = momento

        token = generar_token()
        registro = self.repositorio.agregar_token(
            TokenCorreo(
                usuario_id=usuario.id,
                proposito=proposito.value,
                token_hash=hash_token(token),
                token_cifrado=cifrar(token),
                expira_en=momento + vigencia,
                creado_en=momento,
            )
        )
        publicar(
            self.db,
            tipo_evento.value,
            "token_correo",
            registro.id,
            {"token_id": registro.id, "usuario_id": usuario.id},
        )
        return True

    def _token_valido(self, token: str, proposito: PropositoToken) -> TokenCorreo:
        registro = self.repositorio.token_por_hash(hash_token(token))
        if (
            registro is None
            or registro.proposito != proposito.value
            or registro.usado_en is not None
            or como_utc(registro.expira_en) <= self._momento()
        ):
            raise ErrorValidacion(
                "El enlace no es valido o ya expiro",
                codigo="TOKEN_INVALIDO",
            )
        return registro

    def solicitar_restablecimiento(self, correo: str) -> None:
        """Siempre termina igual, exista o no el correo, para no revelar qué cuentas existen."""
        usuario = self.repositorio.por_correo(correo.strip().lower())
        if (
            usuario is None
            or not usuario.activo
            or usuario.rol == "ESTUDIANTE"
            or usuario.hash_contrasena is None
        ):
            return
        self._emitir_token(
            usuario,
            PropositoToken.RESTABLECER_CONTRASENA,
            timedelta(minutes=self.configuracion.token_restablecer_expira_min),
            TipoEvento.RESTABLECIMIENTO_CONTRASENA_SOLICITADO,
        )
        self.db.commit()

    def restablecer_contrasena(self, token: str, nueva_contrasena: str) -> None:
        registro = self._token_valido(token, PropositoToken.RESTABLECER_CONTRASENA)
        usuario = self.repositorio.por_id(registro.usuario_id)
        if usuario is None or not usuario.activo:
            raise ErrorValidacion("El enlace no es valido o ya expiro", codigo="TOKEN_INVALIDO")

        momento = self._momento()
        usuario.hash_contrasena = hash_contrasena(nueva_contrasena)
        usuario.actualizado_en = momento
        registro.usado_en = momento
        for otro in self.repositorio.tokens_pendientes(usuario.id, registro.proposito):
            otro.usado_en = momento
        self.db.commit()
        with _candado_intentos:
            _intentos_login.pop(usuario.correo.lower(), None)

    # --- Verificación de correo (Fase 9) ----------------------------------------------------

    def solicitar_verificacion_correo(self, usuario: Usuario) -> bool:
        """Reserva la solicitud y publica el evento en la transacción en curso (sin commit).

        Lo llaman M1 (alta de estudiante) y M3 (al convocar). Devuelve False si el correo ya
        está verificado o si se pidió otro enlace hace menos de VERIFICACION_COOLDOWN_MIN.
        El token no se genera aquí: lo genera el observador al construir el correo.
        """
        if usuario.correo_verificado:
            return False
        momento = self._momento()
        ultima = self.repositorio.ultima_verificacion(usuario.id)
        if ultima is not None:
            espera = timedelta(minutes=self.configuracion.verificacion_cooldown_min)
            if momento - como_utc(ultima.creada_en) < espera:
                return False

        verificacion = self.repositorio.agregar_verificacion(
            VerificacionCorreo(
                usuario_id=usuario.id,
                expira_en=momento + timedelta(hours=self.configuracion.verificacion_expira_horas),
                creada_en=momento,
            )
        )
        publicar(
            self.db,
            TipoEvento.VERIFICACION_CORREO_SOLICITADA.value,
            "verificacion_correo",
            verificacion.id,
            {"usuario_id": usuario.id, "verificacion_id": verificacion.id},
        )
        return True

    def preparar_token_verificacion(self, verificacion_id: str) -> tuple[Usuario, str] | None:
        """Genera el token al construir el correo y guarda solo su hash (sin commit).

        Lo llama el observador de correo de M6. Devuelve None si ya no hace falta enviar nada.
        Si el envío falla y el evento se reintenta, se emite un token nuevo: el anterior nunca
        llegó a nadie y no se puede recuperar desde su hash.
        """
        verificacion = self.repositorio.verificacion_por_id(verificacion_id)
        if verificacion is None or verificacion.usada_en is not None:
            return None
        usuario = self.repositorio.por_id(verificacion.usuario_id)
        if usuario is None or not usuario.activo or usuario.correo_verificado:
            return None

        token = generar_token()
        verificacion.token_hash = hash_token(token)
        verificacion.expira_en = self._momento() + timedelta(
            hours=self.configuracion.verificacion_expira_horas
        )
        self.db.flush()
        return usuario, token

    def confirmar_verificacion(self, token: str) -> None:
        verificacion = self.repositorio.verificacion_por_hash(hash_token(token))
        momento = self._momento()
        if (
            verificacion is None
            or verificacion.usada_en is not None
            or como_utc(verificacion.expira_en) <= momento
        ):
            raise ErrorDominio("El enlace no es valido o ya expiro", codigo="TOKEN_INVALIDO")
        usuario = self.repositorio.por_id(verificacion.usuario_id)
        if usuario is None or not usuario.activo:
            raise ErrorDominio("El enlace no es valido o ya expiro", codigo="TOKEN_INVALIDO")

        usuario.correo_verificado = True
        usuario.verificado_en = momento
        verificacion.usada_en = momento
        self.db.commit()

    def reenviar_verificacion(self, correo: str) -> None:
        """Termina siempre igual exista o no el correo, para no revelar qué cuentas existen."""
        usuario = self.repositorio.por_correo(correo.strip().lower())
        if usuario is not None and usuario.activo:
            self.solicitar_verificacion_correo(usuario)
            self.db.commit()
