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
