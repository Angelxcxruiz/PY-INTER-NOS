from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import (
    CodigoRegistro,
    Permiso,
    TokenCorreo,
    Usuario,
    UsuarioPermiso,
    VerificacionCorreo,
)


class RepositorioUsuarios:
    def __init__(self, db: Session) -> None:
        self.db = db

    def agregar_verificacion(self, verificacion: VerificacionCorreo) -> VerificacionCorreo:
        self.db.add(verificacion)
        self.db.flush()
        return verificacion

    def verificacion_por_hash(self, token_hash: str) -> VerificacionCorreo | None:
        return self.db.scalar(
            select(VerificacionCorreo)
            .where(VerificacionCorreo.token_hash == token_hash)
            .with_for_update()
        )

    def verificacion_por_id(self, verificacion_id: str) -> VerificacionCorreo | None:
        return self.db.scalar(
            select(VerificacionCorreo)
            .where(VerificacionCorreo.id == verificacion_id)
            .with_for_update()
        )

    def ultima_verificacion(self, usuario_id: str) -> VerificacionCorreo | None:
        return self.db.scalar(
            select(VerificacionCorreo)
            .where(VerificacionCorreo.usuario_id == usuario_id)
            .order_by(VerificacionCorreo.creada_en.desc())
            .limit(1)
        )

    def agregar_token(self, token: TokenCorreo) -> TokenCorreo:
        self.db.add(token)
        self.db.flush()
        return token

    def token_por_hash(self, token_hash: str) -> TokenCorreo | None:
        return self.db.scalar(
            select(TokenCorreo).where(TokenCorreo.token_hash == token_hash).with_for_update()
        )

    def tokens_pendientes(self, usuario_id: str, proposito: str) -> list[TokenCorreo]:
        return list(
            self.db.scalars(
                select(TokenCorreo).where(
                    TokenCorreo.usuario_id == usuario_id,
                    TokenCorreo.proposito == proposito,
                    TokenCorreo.usado_en.is_(None),
                )
            ).all()
        )

    def por_id(self, usuario_id: str) -> Usuario | None:
        return self.db.get(Usuario, usuario_id)

    def por_correo(self, correo: str) -> Usuario | None:
        return self.db.scalar(select(Usuario).where(Usuario.correo == correo.lower()))

    def listar(
        self, limite: int, desplazamiento: int, estado_cuenta: str | None = None
    ) -> list[Usuario]:
        stmt = select(Usuario)
        if estado_cuenta is not None:
            stmt = stmt.where(Usuario.estado_cuenta == estado_cuenta)
        stmt = stmt.order_by(Usuario.creado_en.desc()).offset(desplazamiento).limit(limite)
        return list(self.db.scalars(stmt).all())

    def solicitudes_docentes(self, limite: int, desplazamiento: int) -> list[Usuario]:
        stmt = (
            select(Usuario)
            .where(Usuario.rol == "DOCENTE", Usuario.estado_cuenta == "PENDIENTE")
            .order_by(Usuario.creado_en)
            .offset(desplazamiento)
            .limit(limite)
        )
        return list(self.db.scalars(stmt).all())

    def contar_solicitudes_docentes(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Usuario)
                .where(Usuario.rol == "DOCENTE", Usuario.estado_cuenta == "PENDIENTE")
            )
            or 0
        )

    def permiso_por_codigo(self, codigo: str) -> Permiso | None:
        return self.db.scalar(select(Permiso).where(Permiso.codigo == codigo))

    # --- Código de verificación del registro (Fase 11b) --------------------------------------

    def agregar_codigo_registro(self, fila: CodigoRegistro) -> CodigoRegistro:
        self.db.add(fila)
        self.db.flush()
        return fila

    def eliminar_codigos_registro(self, usuario_id: str) -> None:
        """Deja al usuario sin código activo: hay una sola fila por usuario."""
        self.db.execute(delete(CodigoRegistro).where(CodigoRegistro.usuario_id == usuario_id))
        self.db.flush()

    def codigo_registro_por_id(self, codigo_id: str) -> CodigoRegistro | None:
        return self.db.scalar(
            select(CodigoRegistro).where(CodigoRegistro.id == codigo_id).with_for_update()
        )

    def ultimo_codigo_registro(self, usuario_id: str) -> CodigoRegistro | None:
        return self.db.scalar(
            select(CodigoRegistro)
            .where(CodigoRegistro.usuario_id == usuario_id)
            .order_by(CodigoRegistro.creada_en.desc())
            .limit(1)
            .with_for_update()
        )

    def agregar(self, usuario: Usuario) -> Usuario:
        self.db.add(usuario)
        self.db.flush()
        return usuario

    def eliminar(self, usuario: Usuario) -> None:
        self.db.delete(usuario)

    def permisos(self, usuario: Usuario) -> list[str]:
        stmt = (
            select(Permiso.codigo)
            .join(UsuarioPermiso, UsuarioPermiso.permiso_id == Permiso.id)
            .where(UsuarioPermiso.usuario_id == usuario.id)
        )
        return list(self.db.scalars(stmt).all())

    def permisos_entidades(self) -> list[Permiso]:
        return list(self.db.scalars(select(Permiso).order_by(Permiso.codigo)).all())

    def permiso_por_id(self, permiso_id: str) -> Permiso | None:
        return self.db.get(Permiso, permiso_id)

    def asignar_permiso(self, usuario: Usuario, permiso: Permiso, asignado_en) -> None:
        existente = self.db.scalar(
            select(UsuarioPermiso).where(
                UsuarioPermiso.usuario_id == usuario.id,
                UsuarioPermiso.permiso_id == permiso.id,
            )
        )
        if existente is None:
            self.db.add(
                UsuarioPermiso(
                    usuario_id=usuario.id,
                    permiso_id=permiso.id,
                    asignado_en=asignado_en,
                )
            )

    def quitar_permiso(self, usuario: Usuario, permiso: Permiso) -> None:
        existente = self.db.scalar(
            select(UsuarioPermiso).where(
                UsuarioPermiso.usuario_id == usuario.id,
                UsuarioPermiso.permiso_id == permiso.id,
            )
        )
        if existente is not None:
            self.db.delete(existente)

    def sustituir_permisos(self, usuario: Usuario, permisos: list[Permiso], ahora) -> None:
        actuales = list(
            self.db.scalars(
                select(UsuarioPermiso).where(UsuarioPermiso.usuario_id == usuario.id)
            ).all()
        )
        for actual in actuales:
            self.db.delete(actual)
        self.db.flush()
        for permiso in permisos:
            self.db.add(
                UsuarioPermiso(
                    usuario_id=usuario.id,
                    permiso_id=permiso.id,
                    asignado_en=ahora,
                )
            )
