import copy
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.clock import Reloj, ahora
from app.core.exceptions import (
    ErrorConflicto,
    ErrorNoEncontrado,
    ErrorPermiso,
    ErrorValidacion,
)
from app.modules.cases.models import (
    Caso,
    ComposicionEscenario,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Puzzle,
    Rubrica,
)
from app.modules.cases.puzzles import (
    MAX_PUZZLES_POR_ESCENARIO,
    validar_contenido,
    verificar,
)
from app.modules.cases.repository import RepositorioCasos
from app.modules.cases.schemas import (
    EscenarioDocenteEntrada,
    OpcionDocenteEntrada,
    PreguntaDocenteEntrada,
    RubricaEntrada,
)
from app.modules.cases.schemas_composicion import ComposicionEntrada
from app.modules.cases.schemas_puzzles import PuzzleEntrada
from app.modules.cases.validacion import validar_caso_para_publicar
from app.modules.files.service import ServicioArchivos


class ServicioCasos:
    def __init__(
        self,
        db: Session,
        reloj: Reloj | None = None,
        archivos: ServicioArchivos | None = None,
    ) -> None:
        self.db = db
        self.repositorio = RepositorioCasos(db)
        self.reloj = reloj
        self._archivos = archivos

    @property
    def archivos(self) -> ServicioArchivos:
        # Los archivos se piden a su propio servicio (nunca a su repositorio ni a sus modelos).
        if self._archivos is None:
            self._archivos = ServicioArchivos(self.db, esta_en_uso=self.archivo_en_uso)
        return self._archivos

    def momento(self):
        return ahora(self.reloj)

    def _puede_todo(self, sesion: dict) -> bool:
        return sesion.get("rol") == "ADMINISTRADOR"

    def _verificar_acceso(self, caso: Caso, sesion: dict) -> None:
        if not self._puede_todo(sesion) and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("Solo el docente creador puede modificar este caso")

    def _verificar_borrador(self, caso: Caso) -> None:
        if caso.estado != "BORRADOR":
            raise ErrorConflicto(
                "El caso publicado o archivado es inmutable",
                detalles={"accion": "Crear una nueva version"},
            )

    def _obtener(self, caso_id: str) -> Caso:
        caso = self.repositorio.por_id(caso_id)
        if caso is None:
            raise ErrorNoEncontrado("Caso no encontrado")
        return caso

    def listar(
        self,
        sesion: dict,
        estado: str | None,
        limite: int,
        desplazamiento: int,
    ) -> list[Caso]:
        usuario_id = None if self._puede_todo(sesion) else sesion["sub"]
        return self.repositorio.listar(usuario_id, estado, limite, desplazamiento)

    def publicados(self, limite: int, desplazamiento: int) -> list[Caso]:
        return self.repositorio.publicados(limite, desplazamiento)

    def obtener(self, caso_id: str, sesion: dict) -> Caso:
        caso = self._obtener(caso_id)
        if not self._puede_todo(sesion) and caso.docente_creador_id != sesion["sub"]:
            raise ErrorPermiso("No puede consultar este caso")
        return caso

    def obtener_para_participacion(self, caso_id: str) -> Caso:
        return self._obtener(caso_id)

    def obtener_vista_estudiante(self, caso_id: str) -> Caso:
        caso = self._obtener(caso_id)
        if caso.estado != "PUBLICADO":
            raise ErrorConflicto("Solo un caso publicado tiene vista de estudiante")
        return caso

    def crear(
        self,
        sesion: dict,
        nombre: str,
        desarrollo_situacional: str,
        contexto_historia: str,
        tiempo_estimado_min: int,
    ) -> Caso:
        momento = self.momento()
        caso = Caso(
            docente_creador_id=sesion["sub"],
            nombre=nombre,
            desarrollo_situacional=desarrollo_situacional,
            contexto_historia=contexto_historia,
            tiempo_estimado_min=tiempo_estimado_min,
            estado="BORRADOR",
            version=1,
            creado_en=momento,
            actualizado_en=momento,
        )
        caso = self.repositorio.agregar(caso)
        self.db.commit()
        self.db.refresh(caso)
        return self._obtener(caso.id)

    def editar(
        self,
        caso_id: str,
        sesion: dict,
        nombre: str | None,
        desarrollo_situacional: str | None,
        contexto_historia: str | None,
        tiempo_estimado_min: int | None,
    ) -> Caso:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        if nombre is not None:
            caso.nombre = nombre
        if desarrollo_situacional is not None:
            caso.desarrollo_situacional = desarrollo_situacional
        if contexto_historia is not None:
            caso.contexto_historia = contexto_historia
        if tiempo_estimado_min is not None:
            caso.tiempo_estimado_min = tiempo_estimado_min
        caso.actualizado_en = self.momento()
        self.db.commit()
        return self._obtener(caso.id)

    def eliminar(self, caso_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        self.repositorio.eliminar_caso(caso)
        self.db.commit()

    def validar(self, caso_id: str) -> list:
        caso = self._obtener(caso_id)
        return validar_caso_para_publicar(caso)

    def publicar(self, caso_id: str, sesion: dict) -> Caso:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        if caso.estado == "PUBLICADO":
            raise ErrorConflicto("El caso ya esta publicado")
        if caso.estado == "ARCHIVADO":
            raise ErrorConflicto("Un caso archivado no se puede publicar")
        errores = validar_caso_para_publicar(caso)
        if errores:
            raise ErrorValidacion(
                "El caso no cumple los requisitos de publicacion",
                detalles={"errores": [error.model_dump() for error in errores]},
            )
        momento = self.momento()
        caso.estado = "PUBLICADO"
        caso.publicado_en = momento
        caso.actualizado_en = momento
        if caso.rubrica is not None:
            caso.rubrica.publicada = True
            caso.rubrica.actualizada_en = momento
        self.db.commit()
        return self._obtener(caso.id)

    def archivar(self, caso_id: str, sesion: dict) -> Caso:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        if caso.estado == "ARCHIVADO":
            return caso
        if caso.estado == "BORRADOR":
            raise ErrorConflicto("Solo se puede archivar un caso publicado")
        momento = self.momento()
        caso.estado = "ARCHIVADO"
        caso.archivado_en = momento
        caso.actualizado_en = momento
        self.db.commit()
        return self._obtener(caso.id)

    def crear_escenario(
        self,
        caso_id: str,
        sesion: dict,
        solicitud: EscenarioDocenteEntrada,
    ) -> Escenario:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        orden = len(caso.escenarios) + 1
        entidad = Escenario(
            caso_id=caso.id,
            orden=orden,
            titulo=solicitud.titulo,
            contexto=solicitud.contexto,
        )
        self.repositorio.registrar(entidad)
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(entidad)
        return entidad

    def editar_escenario(
        self,
        caso_id: str,
        escenario_id: str,
        sesion: dict,
        solicitud: EscenarioDocenteEntrada,
    ) -> Escenario:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self.repositorio.escenario_por_id(escenario_id)
        if escenario is None or escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Escenario no encontrado")
        escenario.titulo = solicitud.titulo
        escenario.contexto = solicitud.contexto
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(escenario)
        return escenario

    def eliminar_escenario(self, caso_id: str, escenario_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self.repositorio.escenario_por_id(escenario_id)
        if escenario is None or escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Escenario no encontrado")
        self.db.delete(escenario)
        self.db.flush()
        self._normalizar_orden(caso.escenarios)
        caso.actualizado_en = self.momento()
        self.db.commit()

    def crear_pregunta(
        self,
        caso_id: str,
        escenario_id: str,
        sesion: dict,
        solicitud: PreguntaDocenteEntrada,
    ) -> Pregunta:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self.repositorio.escenario_por_id(escenario_id)
        if escenario is None or escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Escenario no encontrado")
        pregunta = Pregunta(
            escenario_id=escenario.id,
            orden=len(escenario.preguntas) + 1,
            enunciado=solicitud.enunciado,
        )
        self.repositorio.registrar(pregunta)
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(pregunta)
        return pregunta

    def editar_pregunta(
        self,
        caso_id: str,
        pregunta_id: str,
        sesion: dict,
        solicitud: PreguntaDocenteEntrada,
    ) -> Pregunta:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        pregunta = self.repositorio.pregunta_por_id(pregunta_id)
        if pregunta is None or pregunta.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Pregunta no encontrada")
        pregunta.enunciado = solicitud.enunciado
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(pregunta)
        return pregunta

    def eliminar_pregunta(self, caso_id: str, pregunta_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        pregunta = self.repositorio.pregunta_por_id(pregunta_id)
        if pregunta is None or pregunta.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Pregunta no encontrada")
        escenario = pregunta.escenario
        self.db.delete(pregunta)
        self.db.flush()
        self._normalizar_orden(escenario.preguntas)
        caso.actualizado_en = self.momento()
        self.db.commit()

    # Una sola opción correcta por pregunta: la regla se valida aquí al publicar (validacion.py)
    # y la refuerzan en la base los triggers trg_opcion_validar_correcta_* (migración 0012).
    # Si se intenta marcar una segunda correcta, el trigger responde y el manejador de errores
    # lo traduce a un 409; el editor del frontend desmarca la anterior antes de marcar la nueva.
    def crear_opcion(
        self,
        caso_id: str,
        pregunta_id: str,
        sesion: dict,
        solicitud: OpcionDocenteEntrada,
    ) -> Opcion:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        pregunta = self.repositorio.pregunta_por_id(pregunta_id)
        if pregunta is None or pregunta.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Pregunta no encontrada")
        opcion = Opcion(
            pregunta_id=pregunta.id,
            orden=len(pregunta.opciones) + 1,
            texto=solicitud.texto,
            es_correcta=solicitud.es_correcta,
            justificacion=solicitud.justificacion,
        )
        self.repositorio.registrar(opcion)
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(opcion)
        return opcion

    def editar_opcion(
        self,
        caso_id: str,
        opcion_id: str,
        sesion: dict,
        solicitud: OpcionDocenteEntrada,
    ) -> Opcion:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        opcion = self.repositorio.opcion_por_id(opcion_id)
        if opcion is None or opcion.pregunta.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Opcion no encontrada")
        opcion.texto = solicitud.texto
        opcion.es_correcta = solicitud.es_correcta
        opcion.justificacion = solicitud.justificacion
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(opcion)
        return opcion

    def eliminar_opcion(self, caso_id: str, opcion_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        opcion = self.repositorio.opcion_por_id(opcion_id)
        if opcion is None or opcion.pregunta.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Opcion no encontrada")
        pregunta = opcion.pregunta
        self.db.delete(opcion)
        self.db.flush()
        self._normalizar_orden(pregunta.opciones)
        caso.actualizado_en = self.momento()
        self.db.commit()

    # --- puzzles (Fase 13): no puntúan; solo se editan mientras el caso es borrador -----------

    def _puzzle_del_caso(self, caso: Caso, puzzle_id: str) -> Puzzle:
        puzzle = self.repositorio.puzzle_por_id(puzzle_id)
        if puzzle is None or puzzle.escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Puzzle no encontrado")
        return puzzle

    def crear_puzzle(
        self,
        caso_id: str,
        escenario_id: str,
        sesion: dict,
        solicitud: PuzzleEntrada,
    ) -> Puzzle:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self.repositorio.escenario_por_id(escenario_id)
        if escenario is None or escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Escenario no encontrado")
        contenido = validar_contenido(solicitud.tipo, solicitud.contenido)
        if len(escenario.puzzles) >= MAX_PUZZLES_POR_ESCENARIO:
            raise ErrorConflicto(
                f"Un escenario admite como máximo {MAX_PUZZLES_POR_ESCENARIO} puzzles",
            )
        puzzle = Puzzle(
            escenario_id=escenario.id,
            orden=len(escenario.puzzles) + 1,
            tipo=solicitud.tipo,
            enunciado=solicitud.enunciado.strip(),
            contenido=contenido,
            creado_en=self.momento(),
        )
        self.repositorio.registrar(puzzle)
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(puzzle)
        return puzzle

    def editar_puzzle(
        self,
        caso_id: str,
        puzzle_id: str,
        sesion: dict,
        solicitud: PuzzleEntrada,
    ) -> Puzzle:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        puzzle = self._puzzle_del_caso(caso, puzzle_id)
        puzzle.tipo = solicitud.tipo
        puzzle.enunciado = solicitud.enunciado.strip()
        puzzle.contenido = validar_contenido(solicitud.tipo, solicitud.contenido)
        caso.actualizado_en = self.momento()
        self.db.commit()
        self.db.refresh(puzzle)
        return puzzle

    def eliminar_puzzle(self, caso_id: str, puzzle_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        puzzle = self._puzzle_del_caso(caso, puzzle_id)
        escenario = puzzle.escenario
        self.db.delete(puzzle)
        self.db.flush()
        self._normalizar_orden(escenario.puzzles)
        caso.actualizado_en = self.momento()
        self.db.commit()

    def vista_previa_puzzle(self, caso_id: str, puzzle_id: str, sesion: dict) -> Puzzle:
        """El docente dueño juega su propio puzzle aunque el caso siga en borrador."""
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        return self._puzzle_del_caso(caso, puzzle_id)

    def verificar_puzzle(self, puzzle_id: str, respuesta: dict, sesion: dict) -> bool:
        """Solo dice si acertó. El estudiante únicamente puede verificar puzzles de su caso."""
        puzzle = self.repositorio.puzzle_por_id(puzzle_id)
        if puzzle is None:
            raise ErrorNoEncontrado("Puzzle no encontrado")
        caso_id = puzzle.escenario.caso_id
        rol = sesion.get("rol")
        if rol == "ESTUDIANTE":
            if sesion.get("caso_id") != caso_id:
                raise ErrorPermiso("Este puzzle no pertenece a tu caso")
        elif rol == "DOCENTE":
            self._verificar_acceso(self._obtener(caso_id), sesion)
        elif rol != "ADMINISTRADOR":
            raise ErrorPermiso("No tiene permisos para realizar esta accion")
        return verificar(puzzle.tipo, puzzle.contenido, respuesta)

    def _escenario_del_caso(self, caso: Caso, escenario_id: str) -> Escenario:
        escenario = self.repositorio.escenario_por_id(escenario_id)
        if escenario is None or escenario.caso_id != caso.id:
            raise ErrorNoEncontrado("Escenario no encontrado")
        return escenario

    def obtener_composicion(
        self, caso_id: str, escenario_id: str, sesion: dict
    ) -> ComposicionEscenario | None:
        caso = self.obtener(caso_id, sesion)
        return self._escenario_del_caso(caso, escenario_id).composicion

    def guardar_composicion(
        self,
        caso_id: str,
        escenario_id: str,
        sesion: dict,
        solicitud: ComposicionEntrada,
    ) -> ComposicionEscenario:
        """Crea o reemplaza la composición del escenario (una por escenario, sin historial)."""
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self._escenario_del_caso(caso, escenario_id)

        capas = [capa.model_dump(mode="json") for capa in solicitud.capas]
        imagenes = [capa for capa in capas if capa["tipo"] == "imagen"]
        urls = self.archivos.resolver_urls(
            [capa["archivo_id"] for capa in imagenes],
            {sesion["sub"], caso.docente_creador_id},
        )
        for capa in imagenes:
            capa["url"] = urls[capa["archivo_id"]]

        momento = self.momento()
        composicion = escenario.composicion
        if composicion is None:
            composicion = ComposicionEscenario(escenario=escenario, creado_en=momento)
        composicion.ancho = solicitud.ancho
        composicion.alto = solicitud.alto
        composicion.fondo_color = solicitud.fondo_color
        composicion.capas = capas
        composicion.actualizado_en = momento
        self.repositorio.registrar(composicion)
        caso.actualizado_en = momento
        self.db.commit()
        self.db.refresh(composicion)
        return composicion

    def eliminar_composicion(self, caso_id: str, escenario_id: str, sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        escenario = self._escenario_del_caso(caso, escenario_id)
        if escenario.composicion is None:
            raise ErrorNoEncontrado("El escenario no tiene composición")
        escenario.composicion = None
        caso.actualizado_en = self.momento()
        self.db.commit()

    def archivo_en_uso(self, archivo_id: str) -> bool:
        return self.repositorio.archivo_en_uso(archivo_id)

    def autorizar_edicion_escenario(self, caso_id: str, escenario_id: str, sesion: dict) -> None:
        """El docente es dueño del caso, el caso es borrador y el escenario es de ese caso."""
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        self._escenario_del_caso(caso, escenario_id)

    def reordenar(self, caso_id: str, tipo: str, ids: list[str], sesion: dict) -> None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)
        if tipo not in {"escenarios", "preguntas", "opciones", "puzzles"}:
            raise ErrorValidacion("Tipo de orden no permitido")
        if len(set(ids)) != len(ids):
            raise ErrorValidacion("La lista de ids no puede tener duplicados")

        if tipo == "puzzles":
            # El orden relativo de la lista se aplica dentro de cada escenario.
            mapa = {
                puzzle.id: puzzle for escenario in caso.escenarios for puzzle in escenario.puzzles
            }
            if set(mapa) != set(ids):
                raise ErrorValidacion("La lista debe incluir todos los puzzles del caso")
            contadores: dict[str, int] = {}
            for puzzle_id in ids:
                puzzle = mapa[puzzle_id]
                contadores[puzzle.escenario_id] = contadores.get(puzzle.escenario_id, 0) + 1
                puzzle.orden = contadores[puzzle.escenario_id]
            caso.actualizado_en = self.momento()
            self.db.commit()
            return

        if tipo == "escenarios":
            mapa = {entidad.id: entidad for entidad in caso.escenarios}
            if set(mapa) != set(ids):
                raise ErrorValidacion("La lista debe incluir todos los escenarios")
            entidades = [mapa[entidad_id] for entidad_id in ids]
        elif tipo == "preguntas":
            mapa = {
                pregunta.id: pregunta
                for escenario in caso.escenarios
                for pregunta in escenario.preguntas
            }
            if set(mapa) != set(ids):
                raise ErrorValidacion("La lista debe incluir todas las preguntas del caso")
            entidades = [mapa[entidad_id] for entidad_id in ids]
        else:
            mapa = {
                opcion.id: opcion
                for escenario in caso.escenarios
                for pregunta in escenario.preguntas
                for opcion in pregunta.opciones
            }
            if set(mapa) != set(ids):
                raise ErrorValidacion("La lista debe incluir todas las opciones del caso")
            entidades = [mapa[entidad_id] for entidad_id in ids]
        for orden, entidad in enumerate(entidades, start=1):
            entidad.orden = orden
        caso.actualizado_en = self.momento()
        self.db.commit()

    def obtener_rubrica(self, caso_id: str, sesion: dict) -> Rubrica | None:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        rubrica = self.repositorio.obtener_rubrica(caso.id)
        if rubrica is None:
            raise ErrorNoEncontrado("El caso no tiene rubrica")
        return rubrica

    def reemplazar_rubrica(
        self,
        caso_id: str,
        sesion: dict,
        solicitud: RubricaEntrada,
    ) -> Rubrica:
        caso = self._obtener(caso_id)
        self._verificar_acceso(caso, sesion)
        self._verificar_borrador(caso)

        suma = sum(
            (criterio.peso for criterio in solicitud.criterios),
            start=Decimal("0"),
        )
        if solicitud.escala_min >= solicitud.escala_max:
            raise ErrorValidacion("La escala minima debe ser menor que la escala maxima")
        if solicitud.escala_max > Decimal("100"):
            raise ErrorValidacion("La escala maxima no puede superar 100")
        if not solicitud.escala_min <= solicitud.nota_aprobatoria <= solicitud.escala_max:
            raise ErrorValidacion("La nota aprobatoria debe estar dentro de la escala")
        if solicitud.criterios and suma != Decimal("100"):
            raise ErrorValidacion("Los pesos de los criterios deben sumar exactamente 100")

        rubrica_anterior = self.repositorio.obtener_rubrica(caso.id)
        if rubrica_anterior is not None:
            self.repositorio.quitar_rubrica(rubrica_anterior)

        momento = self.momento()
        rubrica = Rubrica(
            caso_id=caso.id,
            nombre=solicitud.nombre,
            descripcion=solicitud.descripcion,
            escala_min=solicitud.escala_min,
            escala_max=solicitud.escala_max,
            nota_aprobatoria=solicitud.nota_aprobatoria,
            publicada=False,
            creada_en=momento,
            actualizada_en=momento,
        )
        self.repositorio.registrar(rubrica)

        mapa_preguntas = {
            pregunta.id: pregunta
            for escenario in caso.escenarios
            for pregunta in escenario.preguntas
        }
        for orden, criterio_entrada in enumerate(solicitud.criterios, start=1):
            criterio = CriterioRubrica(
                rubrica=rubrica,
                orden=orden,
                nombre=criterio_entrada.nombre,
                descripcion=criterio_entrada.descripcion,
                peso=criterio_entrada.peso,
            )
            self.repositorio.registrar(criterio)
            for pregunta_id in criterio_entrada.pregunta_ids:
                pregunta = mapa_preguntas.get(pregunta_id)
                if pregunta is None:
                    raise ErrorValidacion(
                        "La pregunta del criterio no pertenece al caso",
                        detalles={"pregunta_id": pregunta_id},
                    )
                criterio.preguntas.append(pregunta)
        caso.actualizado_en = momento
        self.db.commit()
        return self.repositorio.obtener_rubrica(caso.id)

    def nueva_version(self, caso_id: str, sesion: dict) -> Caso:
        original = self._obtener(caso_id)
        self._verificar_acceso(original, sesion)
        momento = self.momento()
        copia = Caso(
            docente_creador_id=original.docente_creador_id,
            nombre=original.nombre,
            desarrollo_situacional=original.desarrollo_situacional,
            contexto_historia=original.contexto_historia,
            tiempo_estimado_min=original.tiempo_estimado_min,
            estado="BORRADOR",
            version=original.version + 1,
            caso_origen_id=original.id,
            creado_en=momento,
            actualizado_en=momento,
        )
        self.repositorio.registrar(copia)

        mapa_preguntas: dict[str, Pregunta] = {}
        for escenario in original.escenarios:
            escenario_nuevo = Escenario(
                caso=copia,
                orden=escenario.orden,
                titulo=escenario.titulo,
                contexto=escenario.contexto,
            )
            self.repositorio.registrar(escenario_nuevo)
            if escenario.composicion is not None:
                self.repositorio.registrar(
                    ComposicionEscenario(
                        escenario=escenario_nuevo,
                        ancho=escenario.composicion.ancho,
                        alto=escenario.composicion.alto,
                        fondo_color=escenario.composicion.fondo_color,
                        capas=copy.deepcopy(escenario.composicion.capas),
                        creado_en=momento,
                        actualizado_en=momento,
                    )
                )
            for puzzle in escenario.puzzles:
                self.repositorio.registrar(
                    Puzzle(
                        escenario=escenario_nuevo,
                        orden=puzzle.orden,
                        tipo=puzzle.tipo,
                        enunciado=puzzle.enunciado,
                        contenido=copy.deepcopy(puzzle.contenido),
                        creado_en=momento,
                    )
                )
            for pregunta in escenario.preguntas:
                pregunta_nueva = Pregunta(
                    escenario=escenario_nuevo,
                    orden=pregunta.orden,
                    enunciado=pregunta.enunciado,
                )
                self.repositorio.registrar(pregunta_nueva)
                mapa_preguntas[pregunta.id] = pregunta_nueva
                for opcion in pregunta.opciones:
                    self.repositorio.registrar(
                        Opcion(
                            pregunta=pregunta_nueva,
                            orden=opcion.orden,
                            texto=opcion.texto,
                            es_correcta=opcion.es_correcta,
                            justificacion=opcion.justificacion,
                        )
                    )

        if original.rubrica is not None:
            rubrica_nueva = Rubrica(
                caso=copia,
                nombre=original.rubrica.nombre,
                descripcion=original.rubrica.descripcion,
                escala_min=original.rubrica.escala_min,
                escala_max=original.rubrica.escala_max,
                nota_aprobatoria=original.rubrica.nota_aprobatoria,
                publicada=False,
                creada_en=momento,
                actualizada_en=momento,
            )
            self.repositorio.registrar(rubrica_nueva)
            for criterio in original.rubrica.criterios:
                criterio_nuevo = CriterioRubrica(
                    rubrica=rubrica_nueva,
                    orden=criterio.orden,
                    nombre=criterio.nombre,
                    descripcion=criterio.descripcion,
                    peso=criterio.peso,
                )
                self.repositorio.registrar(criterio_nuevo)
                for pregunta in criterio.preguntas:
                    criterio_nuevo.preguntas.append(mapa_preguntas[pregunta.id])

        self.db.commit()
        return self._obtener(copia.id)

    def _normalizar_orden(self, entidades) -> None:
        # Tras `delete` + `flush` la colección todavía contiene la entidad borrada: se omite.
        vivas = [entidad for entidad in entidades if not inspect(entidad).was_deleted]
        for orden, entidad in enumerate(sorted(vivas, key=lambda item: item.orden), start=1):
            entidad.orden = orden
