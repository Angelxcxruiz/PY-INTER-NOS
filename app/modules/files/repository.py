from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.files.models import ArchivoAdjunto


class RepositorioArchivos:
    def __init__(self, db: Session) -> None:
        self.db = db

    def agregar(self, archivo: ArchivoAdjunto) -> ArchivoAdjunto:
        self.db.add(archivo)
        self.db.flush()
        return archivo

    def por_id(self, archivo_id: str) -> ArchivoAdjunto | None:
        return self.db.get(ArchivoAdjunto, archivo_id)

    def por_ids(self, archivo_ids: list[str]) -> list[ArchivoAdjunto]:
        if not archivo_ids:
            return []
        stmt = select(ArchivoAdjunto).where(ArchivoAdjunto.id.in_(archivo_ids))
        return list(self.db.scalars(stmt).all())

    def listar_de_docente(
        self, docente_id: str, limite: int, desplazamiento: int
    ) -> list[ArchivoAdjunto]:
        stmt = (
            select(ArchivoAdjunto)
            .where(ArchivoAdjunto.docente_id == docente_id)
            .order_by(ArchivoAdjunto.creado_en.desc())
            .offset(desplazamiento)
            .limit(limite)
        )
        return list(self.db.scalars(stmt).all())

    def eliminar(self, archivo: ArchivoAdjunto) -> None:
        self.db.delete(archivo)
        self.db.flush()
