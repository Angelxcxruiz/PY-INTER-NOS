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

### Verificacion de correo del estudiante

- `POST /api/v1/auth/verificar-correo` (publico): `{"token": "..."}`. Token invalido, usado o
  vencido responde 400 con codigo `TOKEN_INVALIDO`.
- `POST /api/v1/auth/reenviar-verificacion` (publico): `{"correo": "..."}`. Responde siempre
  `200` con el mismo mensaje, exista o no el correo. Maximo un envio cada 5 minutos por usuario.

El enlace del correo es `{FRONTEND_URL}/verificar-correo?token=...`; el frontend debe tomar el
`token` y llamar al endpoint anterior. `GET /auth/me` expone `correo_verificado`.

### Restablecer contrasena

- `POST /api/v1/auth/forgot-password` (publico): `{"correo": "..."}`. Responde siempre `202`.
- `POST /api/v1/auth/reset-password` (publico): `{"token": "...", "nueva_contrasena": "..."}`.
  El enlace del correo es `{FRONTEND_URL}/restablecer-contrasena?token=...`.

### Administracion

- `GET /api/v1/admin/users` (ADMINISTRADOR)
- `POST /api/v1/admin/users` (ADMINISTRADOR)
- `GET /api/v1/admin/users/{usuario_id}` (ADMINISTRADOR)
- `PATCH /api/v1/admin/users/{usuario_id}` (ADMINISTRADOR)
- `DELETE /api/v1/admin/users/{usuario_id}` (ADMINISTRADOR)
- `POST /api/v1/admin/users/{usuario_id}/activate` (ADMINISTRADOR)
- `POST /api/v1/admin/users/{usuario_id}/deactivate` (ADMINISTRADOR)
- `GET /api/v1/admin/permissions` (ADMINISTRADOR)
- `PUT /api/v1/admin/users/{usuario_id}/permissions` (ADMINISTRADOR)
- `POST /api/v1/admin/users/{usuario_id}/permissions/{permiso_id}` (ADMINISTRADOR)
- `DELETE /api/v1/admin/users/{usuario_id}/permissions/{permiso_id}` (ADMINISTRADOR)

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

## M6 - Notificaciones y eventos

- `GET /api/v1/notificaciones`
- `GET /api/v1/notificaciones/contador`
- `POST /api/v1/notificaciones/{notificacion_id}/leer`
- `POST /api/v1/notificaciones/leer-todas`
- `GET /api/v1/sessions/{sesion_id}/entregas`
- `POST /api/v1/sessions/{sesion_id}/convocatorias/{convocatoria_id}/reenviar`

## M7 - Seguimiento y reportes

- `GET /api/v1/sessions/{sesion_id}/seguimiento`
- `GET /api/v1/sessions/{sesion_id}/estadisticas`
- `GET /api/v1/cases/{caso_id}/estadisticas`
- `GET /api/v1/espacios-academicos/{espacio_id}/estadisticas`
- `GET /api/v1/sessions/{sesion_id}/reports/participation.csv`
- `GET /api/v1/sessions/{sesion_id}/reports/answers.csv`
