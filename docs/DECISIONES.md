# Decisiones

- La base de ingreso tardio es `sesion.iniciada_en`.
- El repositorio vacio usa MySQL real en pruebas; SQLite no esta permitido.
- Los secretos de entorno no se incorporan a codigo ni imagenes.
- Las pruebas deben usar `TEST_DATABASE_URL`.
- Los servicios controlan las transacciones.
- Los eventos se registran en el outbox dentro de la misma transaccion del cambio.
- La validacion del codigo estudiantil se delegara al servicio del Modulo 3.
- El login estudiantil no revela si el correo existe.
- La limitacion de intentos de login es en memoria para la Fase 1.
- M2 usa `caso_origen_id` para enlazar una nueva version con su caso original.
- La validacion de publicacion acumula todos los errores y los devuelve con ubicacion.
- La vista de estudiante usa schemas independientes y no incluye opciones correctas ni justificaciones.
- M3 delega la obtencion de casos al `ServicioCasos`, sin acceder al repositorio de M2.
- M3 registra temporalmente los eventos de dominio en logs; M6 reemplazara el cuerpo por el outbox real.
- El cierre automatico deja TODOs para M4 y M5; no implementa sus servicios.
- Los codigos se normalizan antes de cifrar, hashear y comparar.
- M4 calcula el limite de ingreso tardio desde `sesion.iniciada_en` multiplicado por `FRACCION_INGRESO_TARDIO`; confirmar con el responsable academico. Cambiar a `inicio_programado` exige modificar una sola linea en `iniciar()`.
- M4 usa el ultimo intento finalizado para reportes y documentacion de M7.
- M4 expira participaciones conservando sus respuestas; M5 las calificara y M8 ejecutara los lotes.
- M5 calcula sin float, redondea solo al final con ROUND_HALF_UP y usa la escala de la rubrica.
- M5 conserva la calificacion existente e impide recalcular.
- M6 solo implementara los eventos `CALIFICACION_REGISTRADA` y `RETROALIMENTACION_AGREGADA`; M5 deja los TODO sin outbox.
- M6 usa outbox transaccional real, backoff configurable y adapters de correo.
- M6 puede leer datos de convocatoria, sesion y usuario para construir mensajes, pero no escribe tablas ajenas.
- El codigo de convocatoria solo se descifra al construir el correo de invitacion.
- M7 usa la calificacion almacenada y nunca recalcula notas.
- M7 ejecuta reportes con aislamiento REPEATABLE READ y una transaccion de solo lectura.
- M7 usa el ultimo intento finalizado para la nota; la seleccion se hace por `finalizada_en`.
- No se usa Git Flow: las ramas protegidas son main y develop y se integra por PR pequeño.

## Fase 8

- El worker es un proceso independiente y no usa el lifespan de FastAPI.
- El seed exige variables administrativas y puede ejecutarse con `--con-sesion`.
- El modo `--reset` elimina solo los datos semilla identificables.
- Docker usa MySQL de desarrollo en el puerto 3308 y MySQL de pruebas en el 3307.

## Fase 9 — Verificación de correo del estudiante (ampliación aprobada por el equipo)

Requisito que no estaba en la especificación original; aprobado por el equipo.

- Al registrar un estudiante (alta por el administrador en M1, o creación al convocar en M3) se
  publica `VERIFICACION_CORREO_SOLICITADA` en el outbox, en la misma transacción que crea al
  usuario. Si el envío falla se aplica el backoff de M6 y nunca se revierte el alta.
- **El token no viaja en el outbox ni se guarda en claro.** El payload lleva solo `usuario_id` y
  `verificacion_id`. El token (`secrets.token_urlsafe(32)`) lo genera el observador de correo al
  construir el mensaje y en la base queda únicamente su hash SHA-256 (`verificacion_correo`).
- La fila de `verificacion_correo` se **reserva al solicitar** (con `token_hash` nulo) y el
  observador solo completa el hash. Se decidió así para que `verificacion_id` exista desde el
  evento y para poder aplicar el límite de reenvío sin esperar al worker. Si el envío falla y el
  evento se reintenta se emite un token nuevo: el anterior nunca salió y no se puede recuperar.
- El observador no escribe en tablas de M1: pide el token a `ServicioUsuarios`
  (`preparar_token_verificacion`), que es quien conoce la regla.
- Vigencia `VERIFICACION_EXPIRA_HORAS` (48 h) y un solo uso. Reenvío limitado a uno cada
  `VERIFICACION_COOLDOWN_MIN` (5 min) por usuario.
- `POST /auth/reenviar-verificacion` responde siempre lo mismo para no revelar qué correos existen.
  Cualquier token inválido, usado o vencido responde 400 con el mismo mensaje.
- Al convocar no se reenvía a quien ya está verificado. Un estudiante existente sin verificar sí
  recibe el enlace (sujeto al límite de reenvío).
- Los docentes y administradores existentes quedan verificados en la migración, y los que cree el
  administrador nacen verificados: la verificación aplica a estudiantes.
- **`EXIGIR_CORREO_VERIFICADO`** (por defecto `false`): con `false` la verificación es informativa y
  el estudiante entra con su código igual; con `true` el validador de M3 rechaza a quien no haya
  verificado, con un mensaje que indica revisar el correo. La comprobación va después de validar el
  código, de modo que un código incorrecto sigue dando el mensaje genérico y no filtra información.
- El seed crea sus usuarios ya verificados para que la demo no dependa del correo.

### Restablecer contraseña (migración 0008)

Solicitado en la misma conversación y aislado en su propia migración (`token_correo`). Aplica a
docentes y administradores (los estudiantes no tienen contraseña). Enlace de un solo uso, 60 min,
una solicitud por minuto. Un enlace nuevo invalida los anteriores. Como el correo necesita el
token, aquí sí se guarda cifrado con Fernet (igual que los códigos de convocatoria) además de su
hash. `POST /auth/forgot-password` responde siempre igual.

### Correcciones encontradas durante esta fase

- La clave de idempotencia del outbox superaba los 128 caracteres de su columna y MySQL rechazaba
  el INSERT al publicar eventos de convocatoria, calificación y retroalimentación. Ahora es un
  SHA-256 (64 caracteres). Pasó desapercibido porque las pruebas anteriores no tocaban MySQL.
- `EMAIL_BACKEND` desconocido ahora falla con un error claro en lugar de enviar a consola, y el
  correo lleva remitente (`SMTP_REMITENTE`).

## Fase 10 — Simulador jugable servido por FastAPI

- **Un solo proceso.** `uvicorn app.main:app --host 0.0.0.0 --port 8000` sirve la API (`/api/v1`) y
  la interfaz (`/app`). Se descartaron React, Node y bundlers: la interfaz se explica y se sustenta
  sin herramientas adicionales. La raíz `/` redirige a `/app/`.
- **Mobile-first.** Se diseñó primero para pantalla pequeña porque la docente entra desde el celular.
- **El tiempo lo manda el servidor.** El temporizador se ancla a `segundos_restantes` de cada
  respuesta del servidor y se resincroniza cada 20 s y al volver a la pestaña; el navegador solo cuenta
  hacia atrás entre dos respuestas. Al llegar a cero consulta al servidor antes de cerrar.
- **RF-14.** Durante el juego solo se usa `GET /cases/{id}/vista-estudiante`, que no trae
  `es_correcta` ni `justificacion`. La corrección se muestra únicamente en `/app/resultado`.
- **`caso_id` en el token del estudiante (cambio autorizado en M1).** El estudiante no tenía forma de
  saber qué caso jugar (`GET /sessions/{id}` es solo para docentes). El validador de M3 ya devolvía
  `caso_id`; ahora `login_estudiante` lo incluye en el JWT junto con `convocatoria_id` y `sesion_id`.
  No cambia ninguna regla de acceso.
- **Corrección en M4 (autorizada).** MySQL devuelve los `DATETIME` sin zona y el reloj `ahora()` los
  trae en UTC; `POST /participations/start/{id}` fallaba con `TypeError` al compararlos. Se normalizan
  con `como_utc()` en las comparaciones y en `calculos.py`, sin cambiar ninguna regla. Lo cubre
  `tests/test_participaciones_mysql.py`, que corre el flujo completo contra MySQL.
- **Seguridad de la interfaz.** Todo el texto que viene de la API entra por `textContent` (nunca
  `innerHTML`), así que un nombre o enunciado con HTML no se ejecuta. Los recursos estáticos llevan
  `?v=<marca de tiempo>` para que un cambio no se quede en la caché del navegador.
- **Hora de Bogotá solo al mostrar.** El formulario de agenda interpreta lo escrito como hora de
  Bogotá (UTC-5, sin horario de verano) y envía UTC a la API.

## Credenciales y secretos

- **Nunca van en el repositorio.** `.env.example` solo trae el marcador `CAMBIAR-EN-PRODUCCION`
  (o valores vacíos) en `JWT_SECRET`, `FERNET_KEY`, `ADMIN_INICIAL_CONTRASENA` y `DOCENTE_PASSWORD`.
  Cada entorno genera los suyos en su `.env`, que está en `.gitignore` y no está versionado.
- **Sin valores por defecto en el código de los scripts.** `scripts/seed.py` y
  `scripts/reset_passwords.py` leen las contraseñas de `obtener_configuracion()` (`.env`), no las
  imprimen y se niegan a ejecutarse si faltan o siguen en `CAMBIAR-EN-PRODUCCION`.
- **Por qué:** el repositorio es público. Un secreto que alguna vez estuvo en él debe darse por
  conocido, aunque después se borre (queda en el historial de git).
- **Cómo generar los secretos:**
  - `JWT_SECRET`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  - `FERNET_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Cómo rotarlos:**
  1. `ADMIN_INICIAL_CONTRASENA` / `DOCENTE_PASSWORD`: cambiar el valor en `.env` y ejecutar
     `python scripts/reset_passwords.py`. No requiere reiniciar la base.
  2. `JWT_SECRET`: cambiar en `.env` y reiniciar la API. Todas las sesiones abiertas se cierran
     (los tokens firmados con la clave anterior dejan de ser válidos).
  3. `FERNET_KEY`: cambiar en `.env` y reiniciar API y worker. Los códigos de convocatoria ya
     guardados quedan ilegibles (siguen validando por su hash, pero «Ver código» falla). Se
     regeneran con `python scripts/rotar_codigos.py` (`--simular` solo lista las afectadas):
     imprime los códigos nuevos una sola vez, junto al correo, y no envía correos.
  4. Si un secreto estuvo expuesto, rotarlo siempre; borrarlo del archivo no basta.
- **Validación de arranque:** `app/core/config.py` ya no tiene valores por defecto para `JWT_SECRET`
  ni `FERNET_KEY`. La API (y los scripts y Alembic, que usan la misma configuración) no arranca
  si faltan, si valen `CAMBIAR-EN-PRODUCCION` o un valor de ejemplo/publicado conocido, o si la
  clave Fernet no tiene formato válido. El mensaje explica cómo generarlas y los errores de
  validación no imprimen los valores (`hide_input_in_errors`). Lo cubre
  `tests/test_config_secretos.py`. `DATABASE_URL` conserva un valor por defecto de desarrollo
  (usuario `inter_nos`, sin secretos de producción).

## Fase 11 — Registro de usuarios con aprobación de docentes (requisito NUEVO)

> **No es parte del diseño original.** La especificación decía que el administrador crea a los
> docentes y que el estudiante solo entra con el código de la convocatoria. El equipo aprobó este
> autorregistro como ampliación posterior.

| Rol | Cómo se crea | Aprobación |
|---|---|---|
| ESTUDIANTE | Se registra solo desde `/app/registro` | Ninguna (tras verificar su correo) |
| DOCENTE | Se registra solo desde `/app/registro` | El administrador debe aprobarlo |
| ADMINISTRADOR | Solo por seed o por otro administrador | — |

- **Migración `0010_registro`:** `usuario.estado_cuenta` (`ACTIVO` por defecto, así los usuarios
  existentes no cambian), `aprobado_en`, `aprobado_por_id` (FK a `usuario`), `motivo_rechazo` y un
  `CHECK` sobre los estados.
- **Docente pendiente:** inicia sesión (para ver su estado) pero el token trae `estado_cuenta` y
  `permisos` vacíos; `obtener_sesion` responde 403 «Tu cuenta está en revisión…» en casos, sesiones
  y reportes. Un `RECHAZADO` recibe 401 `CUENTA_RECHAZADA`.
- **Solicitudes:** `GET /admin/solicitudes` (paginado, cabecera `X-Total-Count`), `aprobar`
  (opcionalmente con permisos; idempotente) y `rechazar` (motivo opcional). Aprobar o rechazar
  publica `DOCENTE_APROBADO` / `DOCENTE_RECHAZADO` y se envía correo al docente.
- **Endurecimiento relacionado (M4):** un estudiante con contraseña ya puede iniciar sesión, así que
  `_verificar_estudiante_convocatoria` exige que el `convocatoria_id` del token coincida con la
  convocatoria. Sin código de convocatoria no se juega; la pantalla «Únete a una sesión» lo pide.
- **Correo duplicado:** 409 con el mismo mensaje sin importar el rol del correo existente.

## Fase 11b — Verificación del registro por código y dominio configurable (requisito NUEVO)

> Tampoco figura en la especificación original. Sustituye el efecto inmediato del registro de la
> Fase 11: la cuenta no sirve hasta verificar el correo.

- **Flujo:** `POST /auth/registro` crea la cuenta `SIN_VERIFICAR` (sin permisos ni acceso) y publica
  `REGISTRO_INICIADO`; el correo lleva un código de 6 dígitos. `POST /auth/registro/verificar` la
  pasa a `ACTIVO` (estudiante) o `PENDIENTE` (docente, que luego aprueba el administrador) y publica
  `REGISTRO_VERIFICADO`. `POST /auth/registro/reenviar` responde siempre lo mismo.
- **Migración `0011_verificacion_registro`:** tabla `codigo_registro` (`id`, `usuario_id` FK con
  `ON DELETE CASCADE`, `codigo_hash` indexado, `expira_en`, `intentos`, `usado_en`, `creada_en`) y
  `CHECK` de `estado_cuenta` ampliado con `SIN_VERIFICAR`. Los usuarios existentes siguen `ACTIVO`.
- **Seguridad del código:** numérico de 6 dígitos con `secrets`; en la base solo se guarda un HASH
  (HMAC-SHA256 con clave derivada de `JWT_SECRET` y ligado al usuario: con solo 10^6 posibilidades,
  un SHA-256 simple se rompería por fuerza bruta si se filtrara la tabla). La comparación usa
  `hmac.compare_digest`; el código se gasta una vez (`usado_en`); vigencia
  `CODIGO_REGISTRO_EXPIRA_MIN` (15), máximo `CODIGO_REGISTRO_MAX_INTENTOS` (5) intentos y un reenvío
  cada `CODIGO_REGISTRO_COOLDOWN_SEG` (60). Todos los fallos (código incorrecto, vencido, usado,
  agotado o correo inexistente) dan el mismo 400 `CODIGO_INVALIDO`, sin revelar si el correo existe.
- **Desviación consciente de lo pedido** («se descifra al construir el correo»): el código no se
  cifra, se genera al construir el correo y de inmediato se guarda solo su hash. Así ni siquiera
  hay algo descifrable en la base. El payload del outbox lleva solo ids
  (`usuario_id`, `codigo_registro_id`); `publicar()` ya rechaza claves como `codigo`.
- **Respuesta de registro:** `{usuario_id, correo, mensaje, vigencia_segundos, reenvio_segundos}`.
  Las dos cifras no son secretas y permiten dibujar los contadores; jamás va el código.
- **Un solo código activo por usuario:** se garantiza en el servicio (borra y crea), no con una
  restricción única en la base.
- **Eventos:** `REGISTRO_VERIFICADO` avisa a todos los administradores cuando el rol es DOCENTE.
  Sustituye a `DOCENTE_REGISTRADO` (de la Fase 11), que ya no se publica pero su suscripción se
  conserva por si hubiera eventos antiguos en el outbox.
- **Login:** una cuenta `SIN_VERIFICAR` recibe 401 `CORREO_SIN_VERIFICAR` (solo tras acertar la
  contraseña) con `detalles.verificar` / `detalles.reenviar`; el frontend la lleva a
  `/app/registro?verificar=<correo>`.
- **Dominio institucional:** `DOMINIO_INSTITUCIONAL` es obligatorio (la API no arranca sin él),
  admite una lista separada por comas y acepta el dominio **y sus subdominios** (`edu.co` vale para
  cualquier `@universidad.edu.co`). Se exige **solo a los estudiantes**: el docente puede registrarse
  con cualquier correo (decisión del equipo), porque igual pasa por verificación de correo y por la
  aprobación del administrador. Lo lee `ServicioUsuarios._dominio_permitido`, la única
  validación, usada por el registro, el login de estudiante y el alta de estudiantes por el
  administrador (`tests/test_dominio.py` lo comprueba). Dominios parecidos
  (`evil-edu.co`, `unihumboldt.edu.co.malo.com`) se rechazan.
- **Ver el código en local (sin Mailpit):** `EMAIL_BACKEND=console` imprime el correo completo en la
  terminal de la API (con `DESPACHO_INMEDIATO=true`) o del worker. Solo para desarrollo.
- **Límites conocidos:** no hay limitación de tasa ni captcha en el registro público (se pueden
  crear cuentas sin verificar y enviar correos masivamente); lo mitigan el cooldown por cuenta y la
  verificación obligatoria, pero para producción conviene un límite por IP (p. ej. en el ALB/WAF).

## Fase 11c — Panel completo del docente (ampliación)

- **Editor de casos en la interfaz** (`docente_casos.js`): crear caso, escenarios, preguntas con
  opciones y justificación, rúbrica (generada automáticamente: un criterio por escenario con pesos
  que suman 100, editable), lista de verificación en vivo y publicación. Un caso publicado no se
  edita: se crea una nueva versión. Las reglas siguen en el servidor (`/cases`).
- **Códigos independientes por estudiante:** al asignar un caso (agendar sesión + convocar), cada
  estudiante recibe su propio código por correo; el docente puede verlo, copiarlo (todos a la vez),
  reenviar el correo, regenerarlo o quitar al estudiante. El detalle muestra nombre y correo reales
  (salen de `/sessions/{id}/seguimiento`) y el estado del correo (`/entregas`).
- **Resultados** (`docente_resultados.js`): seguimiento en vivo (se actualiza cada 15 s con la sesión
  en curso), estadísticas, acierto por pregunta y criterio, detalle por estudiante, retroalimentación,
  autorización de un nuevo intento y descarga de los CSV.
- **Correcciones del servidor que esto requirió** (hallazgos de la auditoría):
  - El docente dueño de la sesión (o el admin) ya puede leer el resultado de sus estudiantes
    (`/participations/{id}/result`, `/convocatorias/{id}/result`); antes daba 403. Otro docente: 403.
  - El estudiante ve la retroalimentación del docente en su resultado (`retroalimentacion`).
  - `/cases/publicados` exige sesión y ya no devuelve la opción correcta ni su justificación.
  - Autorizar una repetición solo es posible con la sesión `EN_CURSO`.
  - `cerrar_sesiones_vencidas` reutilizaba la variable `cerradas` (lista y contador) y fallaba.
  - Compatibilidad con MariaDB anterior a 10.6 (XAMPP): `FOR UPDATE SKIP LOCKED` solo donde existe
    (`bloquear_filas_omitiendo_bloqueadas`); sin esto el outbox, y por tanto los correos, no corría.

## Fase 12 — Triggers y vistas en la base de datos (requisito académico independiente)

> Lo exige el profesor de Bases de Datos. No forma parte de los requisitos funcionales del
> simulador ni del diseño original: es una capa adicional a nivel de motor.

- **Principio:** los servicios en Python siguen validando todo. Los triggers son una **segunda red
  de seguridad** dentro de MySQL (si alguien escribe directo en la base o un servicio olvida una
  regla), no un reemplazo. Todo está en la migración `0012_triggers_vistas` (`upgrade` y `downgrade`
  completos, con `op.execute()` y SQL crudo).
- **Triggers (9 sobre 4 reglas):**
  1. *Auditoría de calificaciones* — `trg_calificacion_after_insert|update|delete` escriben en
     `auditoria_calificacion` (acción, nota anterior y nueva, `CURRENT_USER()`, fecha UTC). Son
     `AFTER` y no `BEFORE` porque la bitácora solo debe registrar lo que de verdad quedó aplicado:
     un `BEFORE` corre antes de comprobar `CHECK` y llaves y dejaría huella de una operación que la
     fila luego rechaza. La tabla no tiene llave foránea a `calificacion` para que el registro de
     un borrado sobreviva a la fila borrada. El `UPDATE` solo audita si cambia `nota_final`.
  2. *Una sola opción correcta* — `trg_opcion_validar_correcta_insert|update` (`BEFORE`) lanzan
     `SIGNAL SQLSTATE '45000'` con «La pregunta ya tiene una opción correcta». En el `UPDATE` se
     excluye la propia fila (`id <> NEW.id`) para que no se bloquee a sí misma. El manejador de
     errores (`error_handlers.py`) traduce ese error (código MySQL 1644) a un `409`
     `REGLA_DE_BASE_DE_DATOS`; cualquier otro error de base sigue siendo un `500` genérico.
  3. *Progreso automático* — `trg_respuesta_after_insert|update|delete` llaman al procedimiento
     `sp_recalcular_progreso`, que cuenta las respuestas, calcula el total de preguntas del caso de
     la sesión y hace `INSERT ... ON DUPLICATE KEY UPDATE` en `progreso_participacion`. El
     procedimiento evita repetir el mismo cálculo en tres triggers.
  4. *Fecha de cierre* — `trg_participacion_before_update` llena `finalizada_en` con
     `UTC_TIMESTAMP(6)` al pasar a `FINALIZADA`, `EXPIRADA` o `CERRADA_POR_SESION` si estaba vacía;
     nunca pisa un valor existente.
- **Vistas (5):** `vista_notas_por_sesion` (una fila por convocado, incluye a quien no participó con
  nota `NULL`), `vista_convocados_estado`, `vista_estadisticas_por_criterio` (porcentaje `NULL` sin
  respuestas, con `NULLIF`; solo cuenta participaciones cerradas), `vista_participaciones_detalle`
  (solo lectura, para RF-15; usa `DISTINCT` para que MySQL la trate como no actualizable) y
  `vista_resumen_docente`. Cada una lleva en la migración un comentario de qué resuelve.
- **Limitaciones de MySQL que conviene saber:**
  - Los borrados en **cascada** por llave foránea **no disparan triggers**: borrar una sesión borra
    sus calificaciones sin dejar auditoría. Por eso `progreso_participacion` tiene su propio
    `ON DELETE CASCADE`.
  - Con el registro binario activo, crear triggers o procedimientos sin `SUPER` exige
    `log_bin_trust_function_creators=1`. Está en `docker-compose.yml` (flag `--log-bin-trust-function-creators=1`),
    en `ci.yml` (`SET GLOBAL` antes de migrar) y debe ir en el *parameter group* de RDS
    (`docs/DESPLIEGUE_AWS.md`). Sin eso la migración falla con el error 1419.
  - El progreso que calcula Python (`ServicioParticipaciones._progreso`) se conserva para el
    endpoint; `progreso_participacion` y las vistas son la fuente a nivel de base de datos.
- **Pruebas:** `tests/test_bd_triggers_vistas.py` (marcador `integracion`, MySQL real): cada trigger,
  cada vista, el 409 del manejador y la ida y vuelta `downgrade 0011` → `upgrade head`.

## Paleta del logo (interfaz)

Las variables de `:root` en `frontend/static/estilos.css` son la **única** fuente de color
(`tests/test_frontend.py` verifica que no haya hex ni `rgb()` con números sueltos fuera de `:root`).
El logo tiene fondo azul-violeta oscuro y dos perfiles entrelazados:

| Familia | Colores | Se usa para |
|---|---|---|
| Cálida | ámbar → naranja (`--degradado-calido`, alias `--acento*`) | avance (`--degradado-avance`: barra de progreso), respuestas acertadas (`--ok`), botones de acción principal, temporizador en cuenta atrás (ámbar, luego naranja y rojo al agotarse) |
| Fría | turquesa → cian (`--degradado-frio`, alias `--neon*`) | contexto, información, retroalimentación, datos del estudiante, estados neutros, botones secundarios informativos (`.boton-info`) |

Textos sobre los degradados: `--sobre-acento` (cálido) y `--sobre-frio` (frío), oscuros por contraste.
Colores con transparencia: `rgb(var(--acento-rgb) / alfa)`. Cambiar la paleta es tocar solo `:root`.
Los valores son una aproximación al logo (no se dispone del archivo original).

El **símbolo del logo** (`frontend/static/logo-simbolo.svg`, dos perfiles enfrentados) es el icono
de carga (`.boton.cargando::after` y `.icono-carga`, girando sobre un disco oscuro) y el favicon
(`favicon.svg`, enlazado en `base.html`). Los SVG llevan sus colores incrustados porque no pueden
leer variables CSS.

## Limitaciones conocidas

- La lista de convocados del docente no trae correo ni nombre (`ConvocatoriaSalida` solo expone
  `estudiante_id`). La interfaz los muestra si los conoce (el administrador los consulta en
  `/admin/users`; el docente, los que convocó en esta pestaña) y si no, muestra el final del id.

- El flujo completo con MySQL real depende de Docker o de una instancia disponible.
- El despliegue AWS queda documentado, pero no se ejecutó en esta fase.
- Amazon SES, ECS y CloudWatch requieren cuentas y permisos externos.
- Las plantillas son simplificadas y deben ser validadas por el área académica.
- El worker no publica métricas externas ni usa una cola además del outbox.
