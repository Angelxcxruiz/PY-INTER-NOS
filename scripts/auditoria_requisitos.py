"""Auditoría de requisitos contra la base real (solo lectura, no modifica nada).

Uso:
    python scripts/auditoria_requisitos.py
    python scripts/auditoria_requisitos.py --url http://localhost:8000

Usa el mismo DATABASE_URL que la API (variable de entorno o .env). Con --url hace además
un GET sin token a /cases/publicados para comprobar que no filtra las respuestas (RF-14).
Termina con código 1 si alguna comprobación falla.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv
from sqlalchemy import inspect, text

load_dotenv()

from app.core.database import engine  # noqa: E402

COLUMNAS_CLAVE = {
    "convocatoria": ["codigo_hash", "codigo_cifrado", "codigo_vigente"],
    "participacion": ["vence_en", "estado", "iniciada_en", "finalizada_en", "motivo_cierre"],
    "respuesta": [
        "participacion_id",
        "pregunta_id",
        "opcion_id",
        "respondida_en",
        "actualizada_en",
    ],
    "calificacion": ["nota_final", "puntaje_detalle", "es_ausencia", "es_parcial"],
    "retroalimentacion_pregunta": ["calificacion_id", "pregunta_id", "justificacion"],
    "retroalimentacion_docente": ["participacion_id", "convocatoria_id", "texto"],
    "evento_outbox": ["tipo", "payload", "estado", "clave_idempotencia"],
    "notificacion": ["usuario_id", "evento_id", "leida_en"],
    "entrega_correo": ["evento_id", "destinatario", "estado", "intentos"],
    "autorizacion_repeticion": ["convocatoria_id", "docente_id", "usada_en"],
}
PALABRAS_PROHIBIDAS = ("codigo", "contrasena", "token", "password")

fallos = 0


def resultado(ok: bool, texto: str, detalle: str = "") -> None:
    global fallos
    if not ok:
        fallos += 1
    marca = "OK   " if ok else "FALLA"
    print(f"  [{marca}] {texto}" + (f"  -> {detalle}" if detalle else ""))


def seccion(titulo: str) -> None:
    print(f"\n== {titulo} ==")


def tablas_y_columnas(conexion) -> None:
    seccion("1. Tablas y columnas clave")
    inspector = inspect(conexion)
    existentes = set(inspector.get_table_names())
    for tabla, columnas in COLUMNAS_CLAVE.items():
        if tabla not in existentes:
            resultado(False, f"tabla {tabla}", "NO EXISTE")
            continue
        presentes = {columna["name"] for columna in inspector.get_columns(tabla)}
        faltan = [columna for columna in columnas if columna not in presentes]
        resultado(not faltan, f"tabla {tabla}", f"faltan: {faltan}" if faltan else "")


def casos(conexion) -> None:
    seccion("2. Integridad de los casos (preguntas, justificaciones, rúbrica)")
    filas = conexion.execute(text("SELECT id, nombre, estado FROM caso ORDER BY creado_en")).all()
    if not filas:
        resultado(False, "hay al menos un caso en la base", "no hay casos (¿se corrió el seed?)")
        return
    for caso_id, nombre, estado in filas:
        marca = " (semilla)" if nombre.startswith("Caso 1.") else ""
        print(f"\n  Caso: {nombre}{marca} [{estado}]")

        preguntas = conexion.execute(
            text(
                "SELECT p.id, p.enunciado, "
                "SUM(CASE WHEN o.es_correcta = 1 THEN 1 ELSE 0 END) AS correctas, "
                "COUNT(o.id) AS opciones "
                "FROM pregunta p JOIN escenario e ON e.id = p.escenario_id "
                "LEFT JOIN opcion o ON o.pregunta_id = p.id "
                "WHERE e.caso_id = :caso GROUP BY p.id, p.enunciado"
            ),
            {"caso": caso_id},
        ).all()
        malas = [
            (enunciado[:50], int(c or 0)) for _, enunciado, c, _ in preguntas if int(c or 0) != 1
        ]
        resultado(
            bool(preguntas) and not malas,
            f"cada pregunta tiene EXACTAMENTE una opcion correcta ({len(preguntas)} preguntas)",
            f"incumplen: {malas}" if malas else "",
        )

        vacias = conexion.execute(
            text(
                "SELECT COUNT(*) FROM opcion o JOIN pregunta p ON p.id = o.pregunta_id "
                "JOIN escenario e ON e.id = p.escenario_id "
                "WHERE e.caso_id = :caso "
                "AND (o.justificacion IS NULL OR TRIM(o.justificacion) = '')"
            ),
            {"caso": caso_id},
        ).scalar()
        resultado(vacias == 0, "ninguna opcion tiene la justificacion vacia", f"{vacias} vacias")

        rubrica = conexion.execute(
            text("SELECT id FROM rubrica WHERE caso_id = :caso"), {"caso": caso_id}
        ).scalar()
        if rubrica is None:
            resultado(estado != "PUBLICADO", "el caso tiene rubrica", "SIN RUBRICA")
            continue
        suma = conexion.execute(
            text("SELECT COALESCE(SUM(peso), 0) FROM criterio_rubrica WHERE rubrica_id = :r"),
            {"r": rubrica},
        ).scalar()
        resultado(float(suma) == 100.0, "los pesos de los criterios suman 100", f"suman {suma}")

        sin_criterio = conexion.execute(
            text(
                "SELECT COUNT(*) FROM pregunta p JOIN escenario e ON e.id = p.escenario_id "
                "WHERE e.caso_id = :caso AND p.id NOT IN "
                "(SELECT cp.pregunta_id FROM criterio_pregunta cp "
                " JOIN criterio_rubrica cr ON cr.id = cp.criterio_id WHERE cr.rubrica_id = :r)"
            ),
            {"caso": caso_id, "r": rubrica},
        ).scalar()
        resultado(
            sin_criterio == 0,
            "toda pregunta esta cubierta por un criterio",
            f"{sin_criterio} sin criterio",
        )


def participaciones(conexion) -> None:
    seccion("3. Participaciones y calificaciones")
    filas = conexion.execute(
        text("SELECT estado, COUNT(*) FROM participacion GROUP BY estado ORDER BY estado")
    ).all()
    if not filas:
        print("  (no hay participaciones todavía)")
    for estado, cantidad in filas:
        print(f"  participaciones {estado:<20} {cantidad}")
    total = conexion.execute(text("SELECT COUNT(*) FROM calificacion")).scalar()
    ausencias = conexion.execute(
        text("SELECT COUNT(*) FROM calificacion WHERE es_ausencia = 1")
    ).scalar()
    parciales = conexion.execute(
        text("SELECT COUNT(*) FROM calificacion WHERE es_parcial = 1")
    ).scalar()
    print(
        f"  calificaciones totales: {total} | con es_ausencia: {ausencias} | parciales: {parciales}"
    )

    duplicadas = conexion.execute(
        text(
            "SELECT COUNT(*) FROM (SELECT participacion_id FROM calificacion "
            "WHERE participacion_id IS NOT NULL GROUP BY participacion_id HAVING COUNT(*) > 1) d"
        )
    ).scalar()
    resultado(
        duplicadas == 0, "ninguna participacion tiene dos calificaciones (RF-13)", f"{duplicadas}"
    )

    sin_calificar = conexion.execute(
        text(
            "SELECT COUNT(*) FROM participacion p LEFT JOIN calificacion c "
            "ON c.participacion_id = p.id WHERE p.estado <> 'EN_PROGRESO' AND c.id IS NULL"
        )
    ).scalar()
    resultado(
        sin_calificar == 0,
        "toda participacion cerrada tiene calificacion",
        f"{sin_calificar} sin calificar",
    )

    vencidas_abiertas = conexion.execute(
        text(
            "SELECT COUNT(*) FROM participacion "
            "WHERE estado = 'EN_PROGRESO' AND vence_en < UTC_TIMESTAMP(6)"
        )
    ).scalar()
    resultado(
        vencidas_abiertas == 0,
        "no hay participaciones EN_PROGRESO ya vencidas (el worker las expira)",
        f"{vencidas_abiertas} vencidas sin cerrar" if vencidas_abiertas else "",
    )

    sesiones_vencidas = conexion.execute(
        text(
            "SELECT COUNT(*) FROM sesion WHERE estado IN ('SIN_INICIAR', 'EN_CURSO') "
            "AND fin_programado < UTC_TIMESTAMP(6) - INTERVAL 1 DAY"
        )
    ).scalar()
    resultado(
        sesiones_vencidas == 0,
        "no hay sesiones abiertas con mas de 1 dia de vencidas (RF-19, lo cierra el worker)",
        f"{sesiones_vencidas} sin cerrar: el worker NO esta corriendo o falla"
        if sesiones_vencidas
        else "",
    )


def buscar_claves(valor, ruta="") -> list[str]:
    encontradas: list[str] = []
    if isinstance(valor, dict):
        for clave, contenido in valor.items():
            subruta = f"{ruta}.{clave}" if ruta else clave
            if any(palabra in str(clave).lower() for palabra in PALABRAS_PROHIBIDAS):
                encontradas.append(subruta)
            encontradas.extend(buscar_claves(contenido, subruta))
    elif isinstance(valor, list):
        for indice, elemento in enumerate(valor):
            encontradas.extend(buscar_claves(elemento, f"{ruta}[{indice}]"))
    return encontradas


def outbox(conexion) -> None:
    seccion("4. Outbox (el payload no debe llevar secretos)")
    estados = conexion.execute(
        text("SELECT estado, COUNT(*) FROM evento_outbox GROUP BY estado ORDER BY estado")
    ).all()
    print("  eventos por estado: " + (", ".join(f"{e}={c}" for e, c in estados) or "(vacio)"))
    sospechosos = []
    revisados = 0
    for _, tipo, payload in conexion.execute(text("SELECT id, tipo, payload FROM evento_outbox")):
        revisados += 1
        datos = json.loads(payload) if isinstance(payload, str | bytes) else payload
        for ruta in buscar_claves(datos):
            sospechosos.append(f"{tipo}:{ruta}")
    resultado(
        not sospechosos,
        f"ningun payload ({revisados}) tiene claves con {'/'.join(PALABRAS_PROHIBIDAS)}",
        f"{sospechosos[:5]}" if sospechosos else "",
    )

    pendientes = conexion.execute(
        text("SELECT COUNT(*) FROM evento_outbox WHERE estado IN ('PENDIENTE', 'PROCESANDO')")
    ).scalar()
    resultado(
        pendientes == 0,
        "no hay eventos sin procesar (si hay, el worker no esta enviando correos)",
        f"{pendientes} pendientes" if pendientes else "",
    )

    sin_hash = conexion.execute(
        text("SELECT COUNT(*) FROM convocatoria WHERE codigo_vigente = 1 AND codigo_hash IS NULL")
    ).scalar()
    resultado(sin_hash == 0, "toda convocatoria vigente tiene codigo_hash", f"{sin_hash} sin hash")


def sondeo_http(url: str) -> None:
    seccion("5. RF-14: ¿/cases/publicados expone las respuestas sin token?")
    destino = url.rstrip("/") + "/api/v1/cases/publicados"
    try:
        with urllib.request.urlopen(destino, timeout=10) as respuesta:  # noqa: S310
            estado, cuerpo = respuesta.status, respuesta.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        estado, cuerpo = error.code, ""
    except OSError as error:
        print(f"  no verificable: no se pudo conectar a {destino} ({error})")
        return
    filtra = '"es_correcta"' in cuerpo or '"justificacion"' in cuerpo
    resultado(
        estado in (401, 403) or not filtra,
        f"GET sin token a {destino} -> HTTP {estado}",
        "EXPONE es_correcta y justificacion a cualquiera" if filtra else "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoria de requisitos (solo lectura)")
    parser.add_argument("--url", help="URL base de la API para el sondeo HTTP de RF-14")
    argumentos = parser.parse_args()

    print(f"Base: {engine.url.render_as_string(hide_password=True)}")
    with engine.connect() as conexion:
        conexion.execute(text("SET SESSION TRANSACTION READ ONLY"))
        tablas_y_columnas(conexion)
        casos(conexion)
        participaciones(conexion)
        outbox(conexion)
    if argumentos.url:
        sondeo_http(argumentos.url)

    print(f"\nResumen: {'TODO OK' if fallos == 0 else f'{fallos} comprobacion(es) FALLAN'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
