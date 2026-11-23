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

## Interfaz web (Fase 10)

La interfaz es una capa de presentación: HTML + CSS + JS sin frameworks ni build, servida por el
mismo proceso de FastAPI.

- `frontend/*.html` son plantillas Jinja2 (`Jinja2Templates`) servidas en `/app/`, `/app/docente`,
  `/app/simulador` y `/app/resultado`.
- `frontend/static/` se publica en `/app/static` con `StaticFiles`.
- El JS consume la API pública con `fetch` bajo `/api/v1`; no hay lógica de negocio en el navegador.
  El token JWT vive en `sessionStorage`.
- Las rutas HTML están en `app/main.py` y no aparecen en Swagger.
- No usa ningún módulo de `app/modules/`: la interfaz solo conoce los endpoints documentados en
  `docs/ENDPOINTS.md`.
