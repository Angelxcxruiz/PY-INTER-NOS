# Arquitectura

Inter Nos usa un monolito modular por capas.

## Flujo obligatorio

`router -> dependencies -> service -> repository -> MySQL`

- Los routers solo reciben solicitudes y delegan.
- Las dependencias resuelven autenticacion y autorizacion.
- Los servicios controlan transacciones y reglas de negocio.
- Los repositorios ejecutan persistencia.
- Los modulos se comunican mediante servicios, nunca mediante repositorios o modelos internos.

## Convenciones

- Identificadores `CHAR(36)` UUID.
- Fechas persistidas en UTC con `DATETIME(6)`.
- America/Bogota solo en presentacion.
- MySQL real con InnoDB y `utf8mb4_unicode_ci`.
- Errores con formato uniforme.
