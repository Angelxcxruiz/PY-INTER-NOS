# Endpoints

Las rutas se publican bajo `/api/v1`. Swagger esta disponible en `/docs`.

La Fase 0 no registra modulos de negocio ni endpoints adicionales.

## Salud

`GET /health`

Ejemplo:

```json
{"estado": "ok"}
```

## M1 - Autenticacion

### Login administrador o docente

`POST /api/v1/auth/login`

```json
{
  "correo": "docente@unal.edu.co",
  "contrasena": "clave-segura"
}
```

### Login estudiante

`POST /api/v1/auth/student-login`

```json
{
  "correo": "estudiante@unal.edu.co",
  "codigo": "<codigo-de-convocatoria>"
}
```
