from datetime import datetime
from threading import Lock
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora
from app.core.config import obtener_configuracion
from app.core.exceptions import (
    ErrorAutenticacion,
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.core.security import (
    crear_jwt,
    hash_contrasena,
    verificar_contrasena,
)
from app.modules.auth.models import Usuario
from app.modules.auth.repository import RepositorioUsuarios


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
            or not verificar_contrasena(contrasena, usuario.hash_contrasena)
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
            creado_en=momento,
            actualizado_en=momento,
        )
        usuario = self.repositorio.agregar(usuario)
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
