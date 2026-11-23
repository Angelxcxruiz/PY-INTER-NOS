from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora, como_utc
from app.core.config import obtener_configuracion
from app.core.enums import PropositoToken, TipoEvento
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
    generar_token,
    hash_contrasena,
    hash_token,
    verificar_contrasena,
)
from app.modules.auth.models import TokenCorreo, Usuario, VerificacionCorreo
from app.modules.auth.repository import RepositorioUsuarios
from app.modules.sessions.events import publicar


class ValidadorConvocatoria(Protocol):
    def __call__(self, correo: str, codigo: str) -> dict: ...


_intentos_login: dict[str, list[datetime]] = {}
_candado_intentos = Lock()


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
        dominios = [
            dominio.strip().lower()
            for dominio in self.configuracion.dominio_institucional.split(",")
            if dominio.strip()
        ]
        correo_normalizado = correo.strip().lower()
        return any(correo_normalizado.endswith("@" + dominio) for dominio in dominios)

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
        if (
            usuario is None
            or not usuario.activo
            or usuario.rol not in {"ADMINISTRADOR", "DOCENTE"}
            or usuario.hash_contrasena is None
            or not verificar_contrasena(usuario.hash_contrasena, contrasena)
        ):
            self._registrar_fallo(correo)
            raise ErrorAutenticacion("Credenciales invalidas")

        permisos = self.repositorio.permisos(usuario)
        token = crear_jwt(
            {"sub": usuario.id, "rol": usuario.rol, "permisos": permisos},
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

    def listar_usuarios(self, limite: int, desplazamiento: int) -> list[Usuario]:
        return self.repositorio.listar(limite, desplazamiento)

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
