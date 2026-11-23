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

## Limitaciones conocidas

- La lista de convocados del docente no trae correo ni nombre (`ConvocatoriaSalida` solo expone
  `estudiante_id`). La interfaz los muestra si los conoce (el administrador los consulta en
  `/admin/users`; el docente, los que convocó en esta pestaña) y si no, muestra el final del id.

- El flujo completo con MySQL real depende de Docker o de una instancia disponible.
- El despliegue AWS queda documentado, pero no se ejecutó en esta fase.
- Amazon SES, ECS y CloudWatch requieren cuentas y permisos externos.
- Las plantillas son simplificadas y deben ser validadas por el área académica.
- El worker no publica métricas externas ni usa una cola además del outbox.
