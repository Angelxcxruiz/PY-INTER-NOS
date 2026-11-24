"""Triggers y vistas a nivel de base de datos (Fase 12, requisito académico de Bases de Datos).

Los servicios siguen validando en Python: los triggers son una SEGUNDA red de seguridad
dentro de MySQL y las vistas dan lecturas ya armadas para reportes.

Notas de implementación:
- Todo el SQL va con op.execute() y sin dos puntos ni porcentajes en el texto, porque
  SQLAlchemy y PyMySQL los interpretan como parámetros.
- Crear triggers y procedimientos con el binlog activo exige SUPER o la variable
  log_bin_trust_function_creators=1 (ver docker-compose.yml, ci.yml y DESPLIEGUE_AWS.md).
- Los borrados en cascada por llave foránea NO disparan triggers en MySQL; por eso
  progreso_participacion tiene su propio ON DELETE CASCADE.

Revision ID: 0012_triggers_vistas
Revises: 0011_verificacion_registro
Create Date: 2026-11-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_triggers_vistas"
down_revision: str | Sequence[str] | None = "0011_verificacion_registro"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS = [
    "trg_calificacion_after_insert",
    "trg_calificacion_after_update",
    "trg_calificacion_after_delete",
    "trg_opcion_validar_correcta_insert",
    "trg_opcion_validar_correcta_update",
    "trg_respuesta_after_insert",
    "trg_respuesta_after_update",
    "trg_respuesta_after_delete",
    "trg_participacion_before_update",
]

VISTAS = [
    "vista_notas_por_sesion",
    "vista_convocados_estado",
    "vista_estadisticas_por_criterio",
    "vista_participaciones_detalle",
    "vista_resumen_docente",
]


def _crear_tablas() -> None:
    # Bitácora de calificaciones. Sin llave foránea a calificacion: el registro de un
    # borrado debe sobrevivir a la fila borrada.
    op.execute(
        """
        CREATE TABLE auditoria_calificacion (
            id CHAR(36) NOT NULL,
            calificacion_id CHAR(36) NOT NULL,
            accion VARCHAR(10) NOT NULL,
            nota_anterior DECIMAL(5,2) NULL,
            nota_nueva DECIMAL(5,2) NULL,
            usuario_bd VARCHAR(150) NOT NULL,
            fecha DATETIME(6) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_auditoria_calificacion_accion
                CHECK (accion IN ('INSERT', 'UPDATE', 'DELETE')),
            INDEX ix_auditoria_calificacion_calificacion (calificacion_id)
        )
        """
    )
    # Avance de cada participación, mantenido por los triggers de respuesta.
    op.execute(
        """
        CREATE TABLE progreso_participacion (
            id CHAR(36) NOT NULL,
            participacion_id CHAR(36) NOT NULL,
            respondidas INT NOT NULL DEFAULT 0,
            total_preguntas INT NOT NULL DEFAULT 0,
            porcentaje DECIMAL(5,2) NOT NULL DEFAULT 0,
            actualizado_en DATETIME(6) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_progreso_participacion UNIQUE (participacion_id),
            CONSTRAINT fk_progreso_participacion
                FOREIGN KEY (participacion_id) REFERENCES participacion (id)
                ON DELETE CASCADE
        )
        """
    )


def _crear_triggers_calificacion() -> None:
    # Se usa AFTER y no BEFORE: la auditoría solo debe registrar cambios que de verdad
    # quedaron aplicados. Un BEFORE se ejecuta antes de comprobar restricciones (CHECK,
    # llaves), y dejaría una huella de una operación que luego la propia fila rechaza.
    # Además un AFTER ya conoce el estado final de la fila y no puede alterarla.
    op.execute(
        """
        CREATE TRIGGER trg_calificacion_after_insert
        AFTER INSERT ON calificacion
        FOR EACH ROW
        INSERT INTO auditoria_calificacion
            (id, calificacion_id, accion, nota_anterior, nota_nueva, usuario_bd, fecha)
        VALUES
            (UUID(), NEW.id, 'INSERT', NULL, NEW.nota_final, CURRENT_USER(), UTC_TIMESTAMP(6))
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_calificacion_after_update
        AFTER UPDATE ON calificacion
        FOR EACH ROW
        BEGIN
            IF NOT (OLD.nota_final <=> NEW.nota_final) THEN
                INSERT INTO auditoria_calificacion
                    (id, calificacion_id, accion, nota_anterior, nota_nueva, usuario_bd, fecha)
                VALUES
                    (UUID(), NEW.id, 'UPDATE', OLD.nota_final, NEW.nota_final,
                     CURRENT_USER(), UTC_TIMESTAMP(6));
            END IF;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_calificacion_after_delete
        AFTER DELETE ON calificacion
        FOR EACH ROW
        INSERT INTO auditoria_calificacion
            (id, calificacion_id, accion, nota_anterior, nota_nueva, usuario_bd, fecha)
        VALUES
            (UUID(), OLD.id, 'DELETE', OLD.nota_final, NULL, CURRENT_USER(), UTC_TIMESTAMP(6))
        """
    )


def _crear_triggers_opcion() -> None:
    # Refuerza en la base la regla que el servicio de casos valida al publicar: una
    # pregunta tiene UNA sola opción correcta. En el UPDATE se excluye la propia fila
    # (id distinto) para que no se bloquee a sí misma.
    op.execute(
        """
        CREATE TRIGGER trg_opcion_validar_correcta_insert
        BEFORE INSERT ON opcion
        FOR EACH ROW
        BEGIN
            IF NEW.es_correcta = 1 AND EXISTS (
                SELECT 1 FROM opcion
                WHERE pregunta_id = NEW.pregunta_id AND es_correcta = 1
            ) THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'La pregunta ya tiene una opción correcta';
            END IF;
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_opcion_validar_correcta_update
        BEFORE UPDATE ON opcion
        FOR EACH ROW
        BEGIN
            IF NEW.es_correcta = 1 AND EXISTS (
                SELECT 1 FROM opcion
                WHERE pregunta_id = NEW.pregunta_id AND es_correcta = 1 AND id <> NEW.id
            ) THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'La pregunta ya tiene una opción correcta';
            END IF;
        END
        """
    )


def _crear_triggers_progreso() -> None:
    # El procedimiento concentra el cálculo para que los tres triggers no lo repitan.
    op.execute(
        """
        CREATE PROCEDURE sp_recalcular_progreso(IN p_participacion_id CHAR(36))
        BEGIN
            DECLARE v_respondidas INT DEFAULT 0;
            DECLARE v_total INT DEFAULT 0;

            SELECT COUNT(*) INTO v_respondidas
            FROM respuesta
            WHERE participacion_id = p_participacion_id;

            SELECT COUNT(*) INTO v_total
            FROM participacion p
            JOIN convocatoria c ON c.id = p.convocatoria_id
            JOIN sesion s ON s.id = c.sesion_id
            JOIN escenario e ON e.caso_id = s.caso_id
            JOIN pregunta q ON q.escenario_id = e.id
            WHERE p.id = p_participacion_id;

            INSERT INTO progreso_participacion
                (id, participacion_id, respondidas, total_preguntas, porcentaje, actualizado_en)
            VALUES
                (UUID(), p_participacion_id, v_respondidas, v_total,
                 IFNULL(ROUND(100 * v_respondidas / NULLIF(v_total, 0), 2), 0),
                 UTC_TIMESTAMP(6))
            ON DUPLICATE KEY UPDATE
                respondidas = VALUES(respondidas),
                total_preguntas = VALUES(total_preguntas),
                porcentaje = VALUES(porcentaje),
                actualizado_en = VALUES(actualizado_en);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_respuesta_after_insert
        AFTER INSERT ON respuesta
        FOR EACH ROW
        CALL sp_recalcular_progreso(NEW.participacion_id)
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_respuesta_after_update
        AFTER UPDATE ON respuesta
        FOR EACH ROW
        CALL sp_recalcular_progreso(NEW.participacion_id)
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_respuesta_after_delete
        AFTER DELETE ON respuesta
        FOR EACH ROW
        CALL sp_recalcular_progreso(OLD.participacion_id)
        """
    )


def _crear_trigger_participacion() -> None:
    # Red de seguridad: si algo cierra una participación sin fecha de cierre, la base la
    # completa. No pisa un valor que ya venga informado.
    op.execute(
        """
        CREATE TRIGGER trg_participacion_before_update
        BEFORE UPDATE ON participacion
        FOR EACH ROW
        BEGIN
            IF NOT (OLD.estado <=> NEW.estado)
               AND NEW.estado IN ('FINALIZADA', 'EXPIRADA', 'CERRADA_POR_SESION')
               AND NEW.finalizada_en IS NULL THEN
                SET NEW.finalizada_en = UTC_TIMESTAMP(6);
            END IF;
        END
        """
    )


def _crear_vistas() -> None:
    # vista_notas_por_sesion: una fila por convocado de cada sesión, con la nota de su
    # último intento (o de su ausencia). Incluye a quien no participó, con nota NULL.
    # Resuelve el reporte de notas del docente sin repetir los JOIN en Python.
    op.execute(
        """
        CREATE VIEW vista_notas_por_sesion AS
        SELECT
            s.id AS sesion_id,
            s.caso_id AS caso_id,
            ca.nombre AS caso_nombre,
            c.id AS convocatoria_id,
            u.id AS estudiante_id,
            u.nombre AS estudiante_nombre,
            u.correo AS estudiante_correo,
            COALESCE(p.estado, 'NO_INICIO') AS estado_participacion,
            COALESCE(k.nota_final, ka.nota_final) AS nota_final,
            COALESCE(k.es_parcial, ka.es_parcial, 0) AS es_parcial,
            COALESCE(k.es_ausencia, ka.es_ausencia, 0) AS es_ausencia,
            (SELECT COUNT(*) FROM participacion x WHERE x.convocatoria_id = c.id)
                AS numero_intentos,
            p.finalizada_en AS finalizada_en
        FROM convocatoria c
        JOIN sesion s ON s.id = c.sesion_id
        JOIN caso ca ON ca.id = s.caso_id
        JOIN usuario u ON u.id = c.estudiante_id
        LEFT JOIN participacion p
            ON p.convocatoria_id = c.id
           AND p.numero_intento = (
               SELECT MAX(m.numero_intento) FROM participacion m
               WHERE m.convocatoria_id = c.id
           )
        LEFT JOIN calificacion k ON k.participacion_id = p.id
        LEFT JOIN calificacion ka ON ka.convocatoria_id = c.id
        """
    )

    # vista_convocados_estado: estado administrativo de cada convocado (código, correo y
    # calificación). Resuelve la pregunta del docente: a quién le falta qué.
    op.execute(
        """
        CREATE VIEW vista_convocados_estado AS
        SELECT
            c.sesion_id AS sesion_id,
            c.id AS convocatoria_id,
            u.id AS estudiante_id,
            u.correo AS correo,
            c.codigo_vigente AS codigo_vigente,
            u.correo_verificado AS correo_verificado,
            (SELECT COUNT(*) FROM participacion x WHERE x.convocatoria_id = c.id)
                AS total_participaciones,
            EXISTS (
                SELECT 1 FROM calificacion k
                WHERE k.convocatoria_id = c.id
                   OR k.participacion_id IN (
                       SELECT x.id FROM participacion x WHERE x.convocatoria_id = c.id
                   )
            ) AS tiene_calificacion,
            EXISTS (
                SELECT 1 FROM calificacion k
                WHERE k.convocatoria_id = c.id AND k.es_ausencia = 1
            ) AS es_ausencia
        FROM convocatoria c
        JOIN usuario u ON u.id = c.estudiante_id
        """
    )

    # vista_estadisticas_por_criterio: acierto acumulado por criterio de la rúbrica
    # (solo participaciones ya cerradas). Un criterio sin respuestas aparece con
    # porcentaje NULL: NULLIF evita la división por cero.
    op.execute(
        """
        CREATE VIEW vista_estadisticas_por_criterio AS
        SELECT
            ru.caso_id AS caso_id,
            cr.id AS criterio_id,
            cr.nombre AS criterio_nombre,
            cr.peso AS peso,
            COUNT(DISTINCT cp.pregunta_id) AS numero_preguntas,
            COUNT(CASE WHEN o.es_correcta = 1 THEN rf.id END) AS aciertos,
            COUNT(rf.id) AS total_respuestas,
            ROUND(
                100 * COUNT(CASE WHEN o.es_correcta = 1 THEN rf.id END)
                / NULLIF(COUNT(rf.id), 0),
                2
            ) AS porcentaje_acierto
        FROM rubrica ru
        JOIN criterio_rubrica cr ON cr.rubrica_id = ru.id
        LEFT JOIN criterio_pregunta cp ON cp.criterio_id = cr.id
        LEFT JOIN (
            SELECT r.id, r.pregunta_id, r.opcion_id
            FROM respuesta r
            JOIN participacion pa ON pa.id = r.participacion_id
            WHERE pa.estado <> 'EN_PROGRESO'
        ) rf ON rf.pregunta_id = cp.pregunta_id
        LEFT JOIN opcion o ON o.id = rf.opcion_id
        GROUP BY ru.caso_id, cr.id, cr.nombre, cr.peso
        """
    )

    # vista_participaciones_detalle: solo lectura, para RF-15 (retroalimentación por
    # pregunta). Una fila por participación y pregunta, con lo elegido, lo correcto y si
    # acertó. El DISTINCT es intencional: cada fila ya es única (participación + pregunta),
    # pero así MySQL no considera la vista actualizable y rechaza INSERT/UPDATE/DELETE.
    op.execute(
        """
        CREATE VIEW vista_participaciones_detalle AS
        SELECT DISTINCT
            p.id AS participacion_id,
            p.numero_intento AS numero_intento,
            p.estado AS estado_participacion,
            s.id AS sesion_id,
            c.id AS convocatoria_id,
            u.nombre AS estudiante_nombre,
            u.correo AS estudiante_correo,
            e.orden AS orden_escenario,
            e.titulo AS escenario_titulo,
            q.id AS pregunta_id,
            q.orden AS orden_pregunta,
            q.enunciado AS enunciado,
            oe.id AS opcion_elegida_id,
            oe.texto AS opcion_elegida,
            oc.id AS opcion_correcta_id,
            oc.texto AS opcion_correcta,
            (r.id IS NOT NULL) AS respondida,
            COALESCE(oe.es_correcta, 0) AS acerto
        FROM participacion p
        JOIN convocatoria c ON c.id = p.convocatoria_id
        JOIN sesion s ON s.id = c.sesion_id
        JOIN usuario u ON u.id = c.estudiante_id
        JOIN escenario e ON e.caso_id = s.caso_id
        JOIN pregunta q ON q.escenario_id = e.id
        LEFT JOIN respuesta r ON r.participacion_id = p.id AND r.pregunta_id = q.id
        LEFT JOIN opcion oe ON oe.id = r.opcion_id
        LEFT JOIN opcion oc ON oc.pregunta_id = q.id AND oc.es_correcta = 1
        """
    )

    # vista_resumen_docente: contadores del panel del docente (casos y sesiones por
    # estado, y participaciones calificadas). Subconsultas por columna para que los
    # conteos no se multipliquen entre sí.
    op.execute(
        """
        CREATE VIEW vista_resumen_docente AS
        SELECT
            u.id AS docente_id,
            u.nombre AS docente_nombre,
            u.correo AS docente_correo,
            (SELECT COUNT(*) FROM caso c
              WHERE c.docente_creador_id = u.id AND c.estado = 'BORRADOR') AS casos_borrador,
            (SELECT COUNT(*) FROM caso c
              WHERE c.docente_creador_id = u.id AND c.estado = 'PUBLICADO') AS casos_publicados,
            (SELECT COUNT(*) FROM caso c
              WHERE c.docente_creador_id = u.id AND c.estado = 'ARCHIVADO') AS casos_archivados,
            (SELECT COUNT(*) FROM sesion s
              WHERE s.docente_id = u.id AND s.estado = 'SIN_INICIAR') AS sesiones_sin_iniciar,
            (SELECT COUNT(*) FROM sesion s
              WHERE s.docente_id = u.id AND s.estado = 'EN_CURSO') AS sesiones_en_curso,
            (SELECT COUNT(*) FROM sesion s
              WHERE s.docente_id = u.id AND s.estado = 'FINALIZADO') AS sesiones_finalizadas,
            (SELECT COUNT(*) FROM calificacion k
              JOIN participacion p ON p.id = k.participacion_id
              JOIN convocatoria c ON c.id = p.convocatoria_id
              JOIN sesion s ON s.id = c.sesion_id
              WHERE s.docente_id = u.id) AS participaciones_calificadas
        FROM usuario u
        WHERE u.rol = 'DOCENTE'
        """
    )


def upgrade() -> None:
    _crear_tablas()
    _crear_triggers_calificacion()
    _crear_triggers_opcion()
    _crear_triggers_progreso()
    _crear_trigger_participacion()
    _crear_vistas()


def downgrade() -> None:
    # Orden inverso a la creación: primero lo que depende (vistas y triggers), después
    # el procedimiento que los triggers invocan y al final las tablas que escriben.
    for vista in reversed(VISTAS):
        op.execute(f"DROP VIEW IF EXISTS {vista}")
    for trigger in reversed(TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    op.execute("DROP PROCEDURE IF EXISTS sp_recalcular_progreso")
    op.execute("DROP TABLE IF EXISTS progreso_participacion")
    op.execute("DROP TABLE IF EXISTS auditoria_calificacion")
