from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.cases.dependencies import obtener_servicio_casos, obtener_sesion_actual
from app.modules.cases.schemas import (
    CasoDocenteSalida,
    CasoEditarEntrada,
    CasoEntrada,
    CasoEstudianteSalida,
    EntradaOrden,
    EscenarioDocenteEntrada,
    EscenarioDocenteSalida,
    OpcionDocenteEntrada,
    OpcionDocenteSalida,
    PreguntaDocenteEntrada,
    PreguntaDocenteSalida,
    ResultadoValidacion,
    RubricaEntrada,
    RubricaSalida,
)
from app.modules.cases.schemas_puzzles import (
    PuzzleDocenteSalida,
    PuzzleEntrada,
    PuzzleEstudianteSalida,
    VerificarPuzzleEntrada,
    VerificarPuzzleSalida,
)
from app.modules.cases.service import ServicioCasos
from app.shared.dependencias_autenticacion import requerir_permiso

router = APIRouter(prefix="/cases", tags=["M2 - Casos academicos"])
router_puzzles = APIRouter(prefix="/puzzles", tags=["M2 - Puzzles"])
permiso_crear_casos = requerir_permiso("CREAR_CASOS")


@router.get("", response_model=list[CasoDocenteSalida])
def listar_casos(
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
    estado: Annotated[str | None, Query()] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[CasoDocenteSalida]:
    casos = servicio.listar(sesion, estado, limite, desplazamiento)
    return [CasoDocenteSalida.model_validate(caso) for caso in casos]


@router.get("/publicados", response_model=list[CasoEstudianteSalida])
def listar_publicados(
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    desplazamiento: Annotated[int, Query(ge=0)] = 0,
) -> list[CasoEstudianteSalida]:
    """Catálogo para usuarios autenticados; nunca expone la respuesta correcta."""
    casos = servicio.publicados(limite, desplazamiento)
    return [CasoEstudianteSalida.model_validate(caso) for caso in casos]


@router.post(
    "",
    response_model=CasoDocenteSalida,
    status_code=201,
)
def crear_caso(
    solicitud: CasoEntrada,
    sesion=Depends(permiso_crear_casos),
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)] = None,
) -> CasoDocenteSalida:
    caso = servicio.crear(
        sesion,
        solicitud.nombre,
        solicitud.desarrollo_situacional,
        solicitud.contexto_historia,
        solicitud.tiempo_estimado_min,
    )
    return CasoDocenteSalida.model_validate(caso)


@router.get("/{caso_id}", response_model=CasoDocenteSalida)
def obtener_caso(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoDocenteSalida:
    return CasoDocenteSalida.model_validate(servicio.obtener(caso_id, sesion))


@router.get("/{caso_id}/vista-estudiante", response_model=CasoEstudianteSalida)
def obtener_vista_estudiante(
    caso_id: str,
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoEstudianteSalida:
    return CasoEstudianteSalida.model_validate(
        servicio.obtener_vista_estudiante(caso_id),
    )


@router.put("/{caso_id}", response_model=CasoDocenteSalida)
def editar_caso(
    caso_id: str,
    solicitud: CasoEditarEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoDocenteSalida:
    caso = servicio.editar(
        caso_id,
        sesion,
        solicitud.nombre,
        solicitud.desarrollo_situacional,
        solicitud.contexto_historia,
        solicitud.tiempo_estimado_min,
    )
    return CasoDocenteSalida.model_validate(caso)


@router.delete("/{caso_id}", status_code=204)
def eliminar_caso(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> None:
    servicio.eliminar(caso_id, sesion)


@router.post("/{caso_id}/publish", response_model=CasoDocenteSalida)
def publicar_caso(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoDocenteSalida:
    return CasoDocenteSalida.model_validate(servicio.publicar(caso_id, sesion))


@router.get("/{caso_id}/validacion", response_model=ResultadoValidacion)
def validar_caso(
    caso_id: str,
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> ResultadoValidacion:
    errores = servicio.validar(caso_id)
    return ResultadoValidacion(valido=not errores, errores=errores)


@router.post("/{caso_id}/new-version", response_model=CasoDocenteSalida)
def nueva_version(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoDocenteSalida:
    return CasoDocenteSalida.model_validate(servicio.nueva_version(caso_id, sesion))


@router.post("/{caso_id}/archive", response_model=CasoDocenteSalida)
def archivar_caso(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> CasoDocenteSalida:
    return CasoDocenteSalida.model_validate(servicio.archivar(caso_id, sesion))


@router.post("/{caso_id}/escenarios", response_model=EscenarioDocenteSalida)
def crear_escenario(
    caso_id: str,
    solicitud: EscenarioDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> EscenarioDocenteSalida:
    return EscenarioDocenteSalida.model_validate(
        servicio.crear_escenario(caso_id, sesion, solicitud),
    )


@router.put("/{caso_id}/escenarios/{escenario_id}", response_model=EscenarioDocenteSalida)
def editar_escenario(
    caso_id: str,
    escenario_id: str,
    solicitud: EscenarioDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> EscenarioDocenteSalida:
    return EscenarioDocenteSalida.model_validate(
        servicio.editar_escenario(caso_id, escenario_id, sesion, solicitud),
    )


@router.delete("/{caso_id}/escenarios/{escenario_id}", status_code=204)
def eliminar_escenario(
    caso_id: str,
    escenario_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> None:
    servicio.eliminar_escenario(caso_id, escenario_id, sesion)


@router.post(
    "/{caso_id}/escenarios/{escenario_id}/preguntas",
    response_model=PreguntaDocenteSalida,
)
def crear_pregunta(
    caso_id: str,
    escenario_id: str,
    solicitud: PreguntaDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> PreguntaDocenteSalida:
    return PreguntaDocenteSalida.model_validate(
        servicio.crear_pregunta(caso_id, escenario_id, sesion, solicitud),
    )


@router.put("/{caso_id}/preguntas/{pregunta_id}", response_model=PreguntaDocenteSalida)
def editar_pregunta(
    caso_id: str,
    pregunta_id: str,
    solicitud: PreguntaDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> PreguntaDocenteSalida:
    return PreguntaDocenteSalida.model_validate(
        servicio.editar_pregunta(caso_id, pregunta_id, sesion, solicitud),
    )


@router.delete("/{caso_id}/preguntas/{pregunta_id}", status_code=204)
def eliminar_pregunta(
    caso_id: str,
    pregunta_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> None:
    servicio.eliminar_pregunta(caso_id, pregunta_id, sesion)


@router.post(
    "/{caso_id}/preguntas/{pregunta_id}/opciones",
    response_model=OpcionDocenteSalida,
)
def crear_opcion(
    caso_id: str,
    pregunta_id: str,
    solicitud: OpcionDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> OpcionDocenteSalida:
    return OpcionDocenteSalida.model_validate(
        servicio.crear_opcion(caso_id, pregunta_id, sesion, solicitud),
    )


@router.put("/{caso_id}/opciones/{opcion_id}", response_model=OpcionDocenteSalida)
def editar_opcion(
    caso_id: str,
    opcion_id: str,
    solicitud: OpcionDocenteEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> OpcionDocenteSalida:
    return OpcionDocenteSalida.model_validate(
        servicio.editar_opcion(caso_id, opcion_id, sesion, solicitud),
    )


@router.delete("/{caso_id}/opciones/{opcion_id}", status_code=204)
def eliminar_opcion(
    caso_id: str,
    opcion_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> None:
    servicio.eliminar_opcion(caso_id, opcion_id, sesion)


@router.post(
    "/{caso_id}/escenarios/{escenario_id}/puzzles",
    response_model=PuzzleDocenteSalida,
    status_code=201,
)
def crear_puzzle(
    caso_id: str,
    escenario_id: str,
    solicitud: PuzzleEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> PuzzleDocenteSalida:
    return PuzzleDocenteSalida.model_validate(
        servicio.crear_puzzle(caso_id, escenario_id, sesion, solicitud),
    )


@router.put("/{caso_id}/puzzles/{puzzle_id}", response_model=PuzzleDocenteSalida)
def editar_puzzle(
    caso_id: str,
    puzzle_id: str,
    solicitud: PuzzleEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> PuzzleDocenteSalida:
    return PuzzleDocenteSalida.model_validate(
        servicio.editar_puzzle(caso_id, puzzle_id, sesion, solicitud),
    )


@router.delete("/{caso_id}/puzzles/{puzzle_id}", status_code=204)
def eliminar_puzzle(
    caso_id: str,
    puzzle_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> None:
    servicio.eliminar_puzzle(caso_id, puzzle_id, sesion)


@router.get("/{caso_id}/puzzles/{puzzle_id}/vista-previa", response_model=PuzzleEstudianteSalida)
def vista_previa_puzzle(
    caso_id: str,
    puzzle_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> PuzzleEstudianteSalida:
    """El puzzle tal como lo verá el estudiante (barajado y sin solución), para el editor."""
    return PuzzleEstudianteSalida.model_validate(
        servicio.vista_previa_puzzle(caso_id, puzzle_id, sesion),
    )


@router_puzzles.post("/{puzzle_id}/verificar", response_model=VerificarPuzzleSalida)
def verificar_puzzle(
    puzzle_id: str,
    solicitud: VerificarPuzzleEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> VerificarPuzzleSalida:
    """Responde solo acertó / no acertó: la solución nunca sale del servidor."""
    return VerificarPuzzleSalida(
        acerto=servicio.verificar_puzzle(puzzle_id, solicitud.respuesta, sesion),
    )


@router.put("/{caso_id}/orden/{tipo}")
def reordenar(
    caso_id: str,
    tipo: str,
    solicitud: EntradaOrden,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> dict[str, str]:
    servicio.reordenar(caso_id, tipo, solicitud.ids, sesion)
    return {"estado": "orden_actualizado"}


@router.get("/{caso_id}/rubrica", response_model=RubricaSalida)
def obtener_rubrica(
    caso_id: str,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> RubricaSalida:
    rubrica = servicio.obtener_rubrica(caso_id, sesion)
    if rubrica is None:
        return None
    return RubricaSalida.model_validate(rubrica)


@router.put("/{caso_id}/rubrica", response_model=RubricaSalida)
def reemplazar_rubrica(
    caso_id: str,
    solicitud: RubricaEntrada,
    sesion: Annotated[dict, Depends(obtener_sesion_actual)],
    servicio: Annotated[ServicioCasos, Depends(obtener_servicio_casos)],
) -> RubricaSalida:
    return RubricaSalida.model_validate(
        servicio.reemplazar_rubrica(caso_id, sesion, solicitud),
    )
