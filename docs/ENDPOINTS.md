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

## M3 - Sesiones y convocatorias

- `POST /api/v1/espacios-academicos`
- `GET /api/v1/espacios-academicos`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{sesion_id}`
- `PUT /api/v1/sessions/{sesion_id}`
- `POST /api/v1/sessions/{sesion_id}/start`
- `POST /api/v1/sessions/{sesion_id}/finish`
- `GET /api/v1/sessions/{sesion_id}/convocatorias`
- `POST /api/v1/sessions/{sesion_id}/convocatorias`
- `DELETE /api/v1/sessions/{sesion_id}/convocatorias/{convocatoria_id}`
- `GET /api/v1/sessions/{sesion_id}/convocatorias/{convocatoria_id}/codigo`
- `POST /api/v1/sessions/{sesion_id}/convocatorias/{convocatoria_id}/codigo/regenerar`

Los endpoints son accesibles a administradores y docentes; los estudiantes no acceden a ellos.

## M4 - Participaciones

- `POST /api/v1/participations/start/{convocatoria_id}` (ESTUDIANTE)
- `GET /api/v1/participations/by-convocatoria/{convocatoria_id}` (ESTUDIANTE)
- `GET /api/v1/participations/{participacion_id}` (ESTUDIANTE propietario)
- `PUT /api/v1/participations/{participacion_id}/answers/{pregunta_id}` (ESTUDIANTE propietario)
- `POST /api/v1/participations/{participacion_id}/finish` (ESTUDIANTE propietario)
- `POST /api/v1/participations/convocatorias/{convocatoria_id}/autorizar-repeticion` (DOCENTE o ADMINISTRADOR)
- `GET /api/v1/participations/convocatorias/{convocatoria_id}/intentos` (DOCENTE o ADMINISTRADOR)

Ejemplo de respuesta:

```json
{
  "opcion_id": "11111111-1111-1111-1111-111111111111"
}
```

## M5 - Evaluacion y retroalimentacion

- `GET /api/v1/participations/{participacion_id}/result`
- `GET /api/v1/convocatorias/{convocatoria_id}/result`
- `POST /api/v1/participations/{participacion_id}/retroalimentacion`
- `POST /api/v1/convocatorias/{convocatoria_id}/retroalimentacion`
- `GET /api/v1/sessions/{sesion_id}/retroalimentaciones`
