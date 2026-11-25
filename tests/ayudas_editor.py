"""Ayudas compartidas por las pruebas del editor visual y de la generación de imágenes."""

from app.core.clock import ahora
from app.core.security import crear_jwt
from app.modules.auth.models import Usuario


def _docente(db, sufijo: str) -> Usuario:
    momento = ahora()
    docente = Usuario(
        nombre=f"Docente{sufijo}",
        correo=f"docente.{sufijo}@gmail.com",
        rol="DOCENTE",
        activo=True,
        correo_verificado=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db.add(docente)
    db.commit()
    return docente


def _cabeceras(usuario_id: str, rol: str = "DOCENTE", permisos=("CREAR_CASOS",)) -> dict:
    token = crear_jwt(
        {"sub": usuario_id, "rol": rol, "permisos": list(permisos), "estado_cuenta": "ACTIVO"}
    )
    return {"Authorization": f"Bearer {token}"}
