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

## M2 - Gestion de casos

- `GET /api/v1/cases`
- `GET /api/v1/cases/publicados`
- `POST /api/v1/cases`
- `GET /api/v1/cases/{caso_id}`
- `GET /api/v1/cases/{caso_id}/vista-estudiante`
- `PUT /api/v1/cases/{caso_id}`
- `DELETE /api/v1/cases/{caso_id}`
- `POST /api/v1/cases/{caso_id}/publish`
- `GET /api/v1/cases/{caso_id}/validacion`
- `POST /api/v1/cases/{caso_id}/new-version`
- `POST /api/v1/cases/{caso_id}/archive`
- `POST /api/v1/cases/{caso_id}/escenarios`
- `PUT /api/v1/cases/{caso_id}/escenarios/{escenario_id}`
- `DELETE /api/v1/cases/{caso_id}/escenarios/{escenario_id}`
- `POST /api/v1/cases/{caso_id}/escenarios/{escenario_id}/preguntas`
- `PUT /api/v1/cases/{caso_id}/preguntas/{pregunta_id}`
- `DELETE /api/v1/cases/{caso_id}/preguntas/{pregunta_id}`
- `POST /api/v1/cases/{caso_id}/preguntas/{pregunta_id}/opciones`
- `PUT /api/v1/cases/{caso_id}/opciones/{opcion_id}`
- `DELETE /api/v1/cases/{caso_id}/opciones/{opcion_id}`
- `PUT /api/v1/cases/{caso_id}/orden/{tipo}`
- `GET /api/v1/cases/{caso_id}/rubrica`
- `PUT /api/v1/cases/{caso_id}/rubrica`

Ejemplo minimo para crear una opcion:

```json
{
  "texto": "Aplicar el protocolo EPICEE",
  "es_correcta": true,
  "justificacion": "Es la actuacion adecuada segun el protocolo."
}
```
