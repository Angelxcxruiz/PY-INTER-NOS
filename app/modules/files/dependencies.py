from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.generacion_imagenes import PuertoGeneradorImagenes, construir_generador
from app.modules.cases.service import ServicioCasos
from app.modules.files.service import ServicioArchivos


def obtener_fabrica_generador() -> Callable[[], PuertoGeneradorImagenes]:
    """El generador se construye tarde (tras validar permisos), no al resolver la dependencia."""
    return construir_generador


def obtener_servicio_archivos(
    db: Annotated[Session, Depends(get_db)],
    fabrica_generador: Annotated[
        Callable[[], PuertoGeneradorImagenes], Depends(obtener_fabrica_generador)
    ],
) -> ServicioArchivos:
    # Lo que depende de casos (imagen en uso, dueño del escenario) lo responde su servicio.
    casos = ServicioCasos(db)
    return ServicioArchivos(
        db,
        esta_en_uso=casos.archivo_en_uso,
        autorizar_escenario=casos.autorizar_edicion_escenario,
        fabrica_generador=fabrica_generador,
    )
