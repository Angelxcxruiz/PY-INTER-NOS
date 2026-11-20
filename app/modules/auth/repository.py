from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import Permiso, Usuario, UsuarioPermiso


class RepositorioUsuarios:
    def __init__(self, db: Session) -> None:
        self.db = db

    def por_id(self, usuario_id: str) -> Usuario | None:
        return self.db.get(Usuario, usuario_id)

    def por_correo(self, correo: str) -> Usuario | None:
        return self.db.scalar(select(Usuario).where(Usuario.correo == correo.lower()))

    def listar(self, limite: int, desplazamiento: int) -> list[Usuario]:
        stmt = (
            select(Usuario).order_by(Usuario.creado_en.desc()).offset(desplazamiento).limit(limite)
        )
        return list(self.db.scalars(stmt).all())

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
