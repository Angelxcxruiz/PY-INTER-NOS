import argparse
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import delete, select

from app.core.clock import ahora
from app.core.config import MARCADOR_SECRETO, obtener_configuracion
from app.core.database import SessionLocal
from app.core.security import cifrar, generar_codigo, hash_codigo, hash_contrasena
from app.modules.auth.models import Permiso, Usuario, UsuarioPermiso
from app.modules.cases.models import (
    Caso,
    CriterioRubrica,
    Escenario,
    Opcion,
    Pregunta,
    Puzzle,
    Rubrica,
)
from app.modules.cases.puzzles import (
    CLASIFICAR,
    EMPAREJAR_CONCEPTOS,
    ORDENAR_SECUENCIA,
    PIEZA_FALTANTE,
    validar_contenido,
)
from app.modules.sessions.models import Convocatoria, EspacioAcademico, Sesion


def asegurar_permiso(db) -> Permiso:
    permiso = db.scalar(select(Permiso).where(Permiso.codigo == "CREAR_CASOS"))
    if permiso is None:
        permiso = Permiso(
            id=str(uuid.uuid4()),
            codigo="CREAR_CASOS",
            nombre="Crear casos",
            descripcion="Permite crear y publicar casos academicos",
        )
        db.add(permiso)
        db.flush()
    return permiso


def asegurar_usuario(db, correo, nombre, rol, contrasena=None) -> tuple[Usuario, bool]:
    usuario = db.scalar(select(Usuario).where(Usuario.correo == correo.lower()))
    if usuario is not None:
        return usuario, False
    usuario = Usuario(
        id=str(uuid.uuid4()),
        nombre=nombre,
        correo=correo.lower(),
        hash_contrasena=hash_contrasena(contrasena) if contrasena else None,
        rol=rol,
        activo=True,
        # Datos de demostración: se dan por verificados para no depender del correo.
        correo_verificado=True,
        verificado_en=ahora(),
        creado_en=ahora(),
        actualizado_en=ahora(),
    )
    db.add(usuario)
    db.flush()
    return usuario, True


def asignar_permiso(db, usuario, permiso) -> bool:
    existente = db.scalar(
        select(UsuarioPermiso).where(
            UsuarioPermiso.usuario_id == usuario.id,
            UsuarioPermiso.permiso_id == permiso.id,
        )
    )
    if existente is not None:
        return False
    db.add(
        UsuarioPermiso(
            usuario_id=usuario.id,
            permiso_id=permiso.id,
            asignado_en=ahora(),
        )
    )
    return True


def opcion(
    pregunta,
    orden,
    texto,
    correcta,
):
    return Opcion(
        id=str(uuid.uuid4()),
        pregunta=pregunta,
        orden=orden,
        texto=texto,
        es_correcta=correcta,
        justificacion="[EJEMPLO — validar con docente] " + texto,
    )


def crear_pregunta(escenario, orden, enunciado, opciones):
    pregunta = Pregunta(
        id=str(uuid.uuid4()),
        escenario=escenario,
        orden=orden,
        enunciado=enunciado,
    )
    for indice, datos in enumerate(opciones, start=1):
        pregunta.opciones.append(opcion(pregunta, indice, datos[0], datos[1]))
    return pregunta


def asegurar_caso(db, docente) -> tuple[Caso, bool]:
    nombre = "Caso 1. Violencia familiar y tentativa de feminicidio"
    caso = db.scalar(select(Caso).where(Caso.nombre == nombre).limit(1))
    if caso is not None:
        return caso, False

    momento = ahora()
    caso = Caso(
        id=str(uuid.uuid4()),
        docente_creador_id=docente.id,
        nombre=nombre,
        desarrollo_situacional=(
            "Una paciente llega acompañada por signos de violencia familiar y "
            "presenta una posible urgencia vital."
        ),
        contexto_historia=(
            "Caso academico basado en violencia de genero y restablecimiento integral de derechos."
        ),
        tiempo_estimado_min=30,
        estado="BORRADOR",
        version=1,
        creado_en=momento,
        actualizado_en=momento,
    )
    db.add(caso)
    db.flush()

    rubrica = Rubrica(
        id=str(uuid.uuid4()),
        caso=caso,
        nombre="Rubrica Caso 1",
        descripcion="Rúbrica publicada para la resolución del caso.",
        escala_min=Decimal("0.00"),
        escala_max=Decimal("5.00"),
        nota_aprobatoria=Decimal("3.00"),
        publicada=False,
        creada_en=momento,
        actualizada_en=momento,
    )
    db.add(rubrica)

    escenario1 = Escenario(
        id=str(uuid.uuid4()),
        caso=caso,
        orden=1,
        titulo="Atención en Hospital (Urgencia vital y crisis)",
        contexto=(
            "La paciente llega a urgencias de un hospital con lesiones "
            "compatibles con violencia familiar."
        ),
    )
    pregunta_inmediata = crear_pregunta(
        escenario1,
        1,
        "¿Cuál debe ser la intervención inmediata ante la urgencia vital y la crisis?",
        [
            ("Aplicar primeros auxilios psicológicos y activar el protocolo EPICEE/SPIKES.", True),
            ("Esperar a que la paciente solicite ayuda nuevamente.", False),
            ("Limitar la atención a la valoración médica física.", False),
            ("Informar a terceros sin consentimiento cuando no exista riesgo.", False),
        ],
    )
    pregunta_normativa = crear_pregunta(
        escenario1,
        2,
        "¿Qué marco normativo y técnico debe orientar la actuación?",
        [
            ("Resolución 459 de 2012, Ley 1257 de 2008 y Ley 2126 de 2021.", True),
            ("Solo las normas internas del hospital.", False),
            ("Únicamente el Código Penal.", False),
            ("Ninguna norma, porque es un caso privado.", False),
        ],
    )
    pregunta_etica = crear_pregunta(
        escenario1,
        3,
        "¿Cuál es la actuación técnica y ética correcta?",
        [
            ("Valorar el riesgo de feminicidio y activar el deber de denuncia.", True),
            ("Archivar el caso si la paciente no firma.", False),
            ("Prometer confidencialidad absoluta ante todo riesgo.", False),
            ("Dejar la decisión en manos de la familia.", False),
        ],
    )

    escenario2 = Escenario(
        id=str(uuid.uuid4()),
        caso=caso,
        orden=2,
        titulo="Comisaría de Familia (Restablecimiento de derechos)",
        contexto=(
            "La situación es remitida a la Comisaría de Familia para "
            "garantizar medidas de protección y restablecer derechos."
        ),
    )
    pregunta_medidas = crear_pregunta(
        escenario2,
        1,
        "¿Cuál es la intervención inmediata en el nuevo escenario?",
        [
            ("Adoptar medidas de protección y activar una ruta de atención.", True),
            ("Cerrar el caso por falta de denuncia formal.", False),
            ("Esperar a que finalice la crisis familiar.", False),
            ("Devolver el proceso a la familia.", False),
        ],
    )
    pregunta_1098 = crear_pregunta(
        escenario2,
        2,
        "¿Qué norma aplica principalmente al restablecimiento de derechos?",
        [
            ("Ley 1098 de 2006, Código de la Infancia y la Adolescencia.", True),
            ("Resolución 459 de 2012, sin relación con menores.", False),
            ("Solo la Ley 1257 de 2008.", False),
            ("Únicamente el reglamento interno.", False),
        ],
    )
    pregunta_etica2 = crear_pregunta(
        escenario2,
        3,
        "¿Cuál debe ser la actuación técnica y ética interinstitucional?",
        [
            ("Coordinar restablecimiento de derechos y articulación entre instituciones.", True),
            ("Actuar aisladamente sin ruta conjunta.", False),
            ("Revelar datos de niñas, niños o adolescentes.", False),
            ("Suspender la protección mientras se define responsabilidad.", False),
        ],
    )

    caso.escenarios.extend([escenario1, escenario2])
    caso.rubrica = rubrica

    criterio1 = CriterioRubrica(
        id=str(uuid.uuid4()),
        rubrica=rubrica,
        orden=1,
        nombre="Intervención inmediata y manejo de crisis",
        descripcion="Preguntas sobre actuación inmediata y medidas de protección.",
        peso=Decimal("40.00"),
    )
    criterio1.preguntas.extend([pregunta_inmediata, pregunta_medidas])

    criterio2 = CriterioRubrica(
        id=str(uuid.uuid4()),
        rubrica=rubrica,
        orden=2,
        nombre="Marco normativo y técnico aplicado",
        descripcion="Preguntas sobre resolución y leyes aplicables.",
        peso=Decimal("30.00"),
    )
    criterio2.preguntas.extend([pregunta_normativa, pregunta_1098])

    criterio3 = CriterioRubrica(
        id=str(uuid.uuid4()),
        rubrica=rubrica,
        orden=3,
        nombre="Actuación técnica y ética",
        descripcion="Preguntas sobre valoración de riesgo y restablecimiento.",
        peso=Decimal("30.00"),
    )
    criterio3.preguntas.extend([pregunta_etica, pregunta_etica2])
    rubrica.criterios.extend([criterio1, criterio2, criterio3])

    caso.estado = "PUBLICADO"
    caso.publicado_en = momento
    caso.actualizado_en = momento
    rubrica.publicada = True
    db.flush()
    return caso, True


MARCA_EJEMPLO = "[EJEMPLO — validar con docente]"

# Puzzles de ejemplo por orden de escenario: (tipo, enunciado, contenido). No puntúan.
PUZZLES_EJEMPLO = {
    1: [
        (
            ORDENAR_SECUENCIA,
            "Ordena los pasos de los primeros auxilios psicológicos.",
            {
                "tiempo_seg": 45,
                "pasos": [
                    "Observar: valorar la seguridad y las necesidades de la persona",
                    "Escuchar: acompañar sin juzgar ni presionar",
                    "Calmar: ayudar a regular la crisis",
                    "Conectar: orientar hacia apoyo y servicios",
                ],
            },
        ),
        (
            EMPAREJAR_CONCEPTOS,
            "Une cada norma con su tema.",
            {
                "tiempo_seg": 60,
                "pares": [
                    {
                        "termino": "Ley 1257 de 2008",
                        "definicion": "Prevención y sanción de violencias contra la mujer",
                    },
                    {"termino": "Ley 2126 de 2021", "definicion": "Comisarías de Familia"},
                    {
                        "termino": "Resolución 459 de 2012",
                        "definicion": "Atención en salud a víctimas de violencia sexual",
                    },
                    {
                        "termino": "Ley 1098 de 2006",
                        "definicion": "Código de la Infancia y la Adolescencia",
                    },
                ],
            },
        ),
    ],
    2: [
        (
            CLASIFICAR,
            "Clasifica cada acción según quién la lidera.",
            {
                "tiempo_seg": 60,
                "categorias": ["Sector salud", "Comisaría de Familia"],
                "elementos": [
                    {"texto": "Primeros auxilios psicológicos", "categoria": "Sector salud"},
                    {"texto": "Valoración clínica del riesgo", "categoria": "Sector salud"},
                    {"texto": "Medidas de protección", "categoria": "Comisaría de Familia"},
                    {
                        "texto": "Restablecimiento de derechos",
                        "categoria": "Comisaría de Familia",
                    },
                ],
            },
        ),
        (
            PIEZA_FALTANTE,
            "Completa la ruta de atención: ¿qué paso falta?",
            {
                "tiempo_seg": 30,
                "serie": [
                    "Detectar",
                    "Valorar el riesgo",
                    "Proteger",
                    "Remitir",
                    "Hacer seguimiento",
                ],
                "faltante": 3,
                "distractores": ["Archivar", "Esperar"],
            },
        ),
    ],
}


def asegurar_puzzles(db, caso) -> int:
    """Agrega los puzzles de ejemplo a los escenarios que aún no tienen ninguno."""
    creados = 0
    momento = ahora()
    for escenario in caso.escenarios:
        ejemplos = PUZZLES_EJEMPLO.get(escenario.orden, [])
        if not ejemplos or escenario.puzzles:
            continue
        for orden, (tipo, enunciado, contenido) in enumerate(ejemplos, start=1):
            db.add(
                Puzzle(
                    id=str(uuid.uuid4()),
                    escenario_id=escenario.id,
                    orden=orden,
                    tipo=tipo,
                    enunciado=f"{MARCA_EJEMPLO} {enunciado}",
                    contenido=validar_contenido(tipo, contenido),
                    creado_en=momento,
                )
            )
            creados += 1
    db.flush()
    return creados


def reset_demo(db) -> None:
    nombre = "Caso 1. Violencia familiar y tentativa de feminicidio"
    casos = list(db.scalars(select(Caso).where(Caso.nombre == nombre)).all())
    for caso in casos:
        db.execute(delete(Sesion).where(Sesion.caso_id == caso.id))
        db.flush()
    db.execute(delete(Caso).where(Caso.nombre == nombre))
    db.flush()
    dominio = obtener_configuracion().dominio_principal
    correo_demo = [f"docente1@{dominio}", f"docente2@{dominio}"] + [
        f"estudiante{i}@{dominio}" for i in range(1, 6)
    ]
    usuarios_demo = list(db.scalars(select(Usuario).where(Usuario.correo.in_(correo_demo))).all())
    ids_docentes = [usuario.id for usuario in usuarios_demo if usuario.rol == "DOCENTE"]
    if ids_docentes:
        db.execute(delete(EspacioAcademico).where(EspacioAcademico.docente_id.in_(ids_docentes)))
        db.flush()
    db.execute(delete(Usuario).where(Usuario.correo.in_(correo_demo)))
    db.flush()


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Semilla de Inter Nos")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--con-sesion", action="store_true")
    args = parser.parse_args()

    config = obtener_configuracion()
    if (
        not config.admin_inicial_nombre
        or not config.admin_inicial_correo
        or not config.admin_inicial_contrasena
        or not config.docente_password
    ):
        print(
            "Error: defina ADMIN_INICIAL_NOMBRE, ADMIN_INICIAL_CORREO, ADMIN_INICIAL_CONTRASENA "
            "y DOCENTE_PASSWORD en el .env",
            file=sys.stderr,
        )
        return 2
    if MARCADOR_SECRETO in (config.admin_inicial_contrasena, config.docente_password):
        print(
            f"Error: ADMIN_INICIAL_CONTRASENA o DOCENTE_PASSWORD siguen en {MARCADOR_SECRETO}. "
            "Escriba contraseñas propias en el .env antes de ejecutar el seed.",
            file=sys.stderr,
        )
        return 2

    usuarios_creados = 0
    permisos_asignados = 0
    casos_creados = 0
    sesiones_creadas = 0

    with SessionLocal() as db:
        if args.reset:
            reset_demo(db)
            db.commit()

        permiso = asegurar_permiso(db)
        admin, creado = asegurar_usuario(
            db,
            config.admin_inicial_correo,
            config.admin_inicial_nombre,
            "ADMINISTRADOR",
            config.admin_inicial_contrasena,
        )
        usuarios_creados += int(creado)

        docente_password = config.docente_password
        docente1, creado = asegurar_usuario(
            db,
            f"docente1@{config.dominio_principal}",
            "Docente Uno",
            "DOCENTE",
            docente_password,
        )
        usuarios_creados += int(creado)
        permisos_asignados += int(asignar_permiso(db, docente1, permiso))

        docente2, creado = asegurar_usuario(
            db,
            f"docente2@{config.dominio_principal}",
            "Docente Dos",
            "DOCENTE",
            docente_password,
        )
        usuarios_creados += int(creado)

        estudiantes = []
        for indice in range(1, 6):
            estudiante, creado = asegurar_usuario(
                db,
                f"estudiante{indice}@{config.dominio_principal}",
                f"Estudiante {indice}",
                "ESTUDIANTE",
                None,
            )
            usuarios_creados += int(creado)
            estudiantes.append(estudiante)

        caso, creado_caso = asegurar_caso(db, docente1)
        casos_creados += int(creado_caso)
        puzzles_creados = asegurar_puzzles(db, caso)
        db.commit()
        if puzzles_creados:
            print(f"Puzzles de ejemplo creados: {puzzles_creados}")

        codigos = []
        if args.con_sesion:
            espacio = db.scalar(
                select(EspacioAcademico).where(
                    EspacioAcademico.docente_id == docente1.id,
                    EspacioAcademico.nombre == "Psicología Social — Grupo 1",
                )
            )
            if espacio is None:
                espacio = EspacioAcademico(
                    id=str(uuid.uuid4()),
                    nombre="Psicología Social — Grupo 1",
                    codigo="PSG1",
                    docente_id=docente1.id,
                    creado_en=ahora(),
                )
                db.add(espacio)
                db.flush()

            inicio = ahora() + timedelta(days=1)
            sesion = db.scalar(
                select(Sesion).where(
                    Sesion.caso_id == caso.id,
                    Sesion.docente_id == docente1.id,
                    Sesion.estado == "SIN_INICIAR",
                )
            )
            if sesion is None:
                sesion = Sesion(
                    id=str(uuid.uuid4()),
                    caso_id=caso.id,
                    docente_id=docente1.id,
                    espacio_academico_id=espacio.id,
                    inicio_programado=inicio,
                    fin_programado=inicio + timedelta(hours=2),
                    tiempo_maximo_min=30,
                    lugar_fisico="Sala 101",
                    mensaje_personalizado="Bienvenido al caso semilla.",
                    estado="SIN_INICIAR",
                    creada_en=ahora(),
                )
                db.add(sesion)
                db.flush()
                sesiones_creadas += 1

            for estudiante in estudiantes:
                convocatoria = db.scalar(
                    select(Convocatoria).where(
                        Convocatoria.sesion_id == sesion.id,
                        Convocatoria.estudiante_id == estudiante.id,
                    )
                )
                if convocatoria is None:
                    codigo = generar_codigo(8)
                    convocatoria = Convocatoria(
                        id=str(uuid.uuid4()),
                        sesion_id=sesion.id,
                        estudiante_id=estudiante.id,
                        codigo_cifrado=cifrar(codigo),
                        codigo_hash=hash_codigo(codigo),
                        codigo_vigente=True,
                        creada_en=ahora(),
                    )
                    db.add(convocatoria)
                    codigos.append((estudiante.correo, codigo))
            db.commit()

    print("Resumen del seed:")
    print(f"- Usuarios creados: {usuarios_creados}")
    print("- Permiso CREAR_CASOS: asegurado")
    print(f"- Permisos asignados: {permisos_asignados}")
    print(f"- Casos creados: {casos_creados}")
    print(f"- Sesiones creadas: {sesiones_creadas}")
    print(f"- Administrador: {config.admin_inicial_correo}")
    print("- Docente 1:", f"docente1@{config.dominio_principal}")
    print("- Docente 2:", f"docente2@{config.dominio_principal}")
    print("- Estudiantes: estudiante1@... a estudiante5@...")
    if args.con_sesion:
        for correo, codigo in codigos:
            print(f"- Codigo demo {correo}: {codigo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
