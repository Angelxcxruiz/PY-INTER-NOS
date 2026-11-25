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

El token del estudiante (rol `ESTUDIANTE`) trae en sus claims `convocatoria_id`, `sesion_id` y
`caso_id`; la interfaz los usa para saber qué caso jugar.

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

### Registro con verificacion por codigo (requisito nuevo, Fase 11/11b)

Todos publicos (sin token). El codigo de 6 digitos llega por correo y nunca se devuelve en la API.

- `POST /api/v1/auth/registro`: `{"nombre", "correo", "contrasena", "rol"}` con `rol` =
  `ESTUDIANTE` o `DOCENTE`. Contrasena minima de 8; el dominio de `DOMINIO_INSTITUCIONAL` se exige
  solo al estudiante (422 si no); el docente puede usar cualquier correo. Correo ya registrado: 409 con mensaje generico. Responde `201`
  `{usuario_id, correo, mensaje, vigencia_segundos, reenvio_segundos}`; la cuenta queda
  `SIN_VERIFICAR`.
- `POST /api/v1/auth/registro/verificar`: `{"correo", "codigo"}`. Correcto: `200`
  `{mensaje, rol, estado_cuenta}` (`ACTIVO` estudiante, `PENDIENTE` docente). Incorrecto, vencido,
  usado o con intentos agotados: `400` `CODIGO_INVALIDO` (mismo mensaje siempre).
- `POST /api/v1/auth/registro/reenviar`: `{"correo"}`. Siempre `200` con el mismo cuerpo. Un envio
  cada `CODIGO_REGISTRO_COOLDOWN_SEG`.
- Login de una cuenta `SIN_VERIFICAR`: `401` `CORREO_SIN_VERIFICAR`. Cuenta rechazada: `401`
  `CUENTA_RECHAZADA`.

### Solicitudes de docentes (ADMINISTRADOR)

- `GET /api/v1/admin/solicitudes`: docentes `PENDIENTE` (paginado; total en `X-Total-Count`).
- `POST /api/v1/admin/solicitudes/{usuario_id}/aprobar`: `{"permisos": ["CREAR_CASOS"]}` opcional.
- `POST /api/v1/admin/solicitudes/{usuario_id}/rechazar`: `{"motivo": "..."}` opcional.
- `GET /api/v1/admin/users?estado_cuenta=PENDIENTE` filtra por estado; la respuesta incluye
  `estado_cuenta`.

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

Puzzles lógicos (Fase 13; no puntúan; 0 a 3 por escenario; `tipo` en `ORDENAR_SECUENCIA`,
`EMPAREJAR_CONCEPTOS`, `PIEZA_FALTANTE`, `CLASIFICAR`, con `contenido` validado por tipo):

- `POST /api/v1/cases/{caso_id}/escenarios/{escenario_id}/puzzles` (DOCENTE, 201)
- `PUT /api/v1/cases/{caso_id}/puzzles/{puzzle_id}` (DOCENTE)
- `DELETE /api/v1/cases/{caso_id}/puzzles/{puzzle_id}` (DOCENTE, 204)
- `GET /api/v1/cases/{caso_id}/puzzles/{puzzle_id}/vista-previa` (DOCENTE: lo ve como el estudiante)
- `PUT /api/v1/cases/{caso_id}/orden/puzzles` (DOCENTE: orden relativo dentro de cada escenario)
- `POST /api/v1/puzzles/{puzzle_id}/verificar` (ESTUDIANTE del caso, DOCENTE dueño o ADMIN).
  Recibe `{"respuesta": ...}` y devuelve solo `{"acerto": true|false}`, sin revelar la solución.

`GET /cases/{caso_id}/vista-estudiante` incluye los puzzles con los elementos barajados y **sin
solución**.

Composición del escenario (Fase 14, editor visual de escenarios; una por escenario, solo en borrador):

- `GET /api/v1/cases/{caso_id}/escenarios/{escenario_id}/composicion` (DOCENTE dueño; `null` si no hay)
- `PUT /api/v1/cases/{caso_id}/escenarios/{escenario_id}/composicion` (crea o reemplaza; 409 si el caso no es borrador)
- `DELETE /api/v1/cases/{caso_id}/escenarios/{escenario_id}/composicion` (204)

Cuerpo del `PUT`: `ancho`, `alto`, `fondo_color` (`#RRGGBB`) y `capas`. Cada capa lleva `tipo`
(`imagen`, `texto`, `forma` o `icono`), `id`, `orden`, `x`, `y`, `ancho` y `alto` opcionales, y sus
campos propios:

```json
{
  "ancho": 1280, "alto": 720, "fondo_color": "#0b0c2b",
  "capas": [
    {"tipo": "imagen", "id": "fondo", "orden": 1, "archivo_id": "<uuid de /archivos>", "ajuste": "cubrir", "x": 0, "y": 0, "ancho": 1280, "alto": 720},
    {"tipo": "texto", "id": "t1", "orden": 2, "x": 80, "y": 60, "ancho": 600, "contenido": "El pasillo", "tamano": 56, "color": "#ffffff", "alineacion": "centro", "negrita": true, "cursiva": false},
    {"tipo": "forma", "id": "f1", "orden": 3, "forma": "rectangulo_redondeado", "relleno": "#14b8a6", "borde_color": null, "borde_grosor": 0, "opacidad": 0.6, "x": 60, "y": 400, "ancho": 360, "alto": 200},
    {"tipo": "icono", "id": "i1", "orden": 4, "icono": "ojo", "color": "#fbbf24", "x": 900, "y": 80, "ancho": 96}
  ]
}
```

La `url` de las capas de imagen la pone el servidor. `GET /cases/{caso_id}/vista-estudiante` y los
escenarios del docente traen `composicion` (o `null`) dentro de cada escenario.

Archivos del editor visual (módulo `files`; requieren el permiso `CREAR_CASOS`):

- `POST /api/v1/archivos/escenarios` (multipart, campo `archivo`; JPG o PNG, máximo 5 MB → 201; 413 si pesa
  más, 415 si no es JPG/PNG de verdad, 422 si está vacío)
- `GET /api/v1/archivos` (las imágenes del docente que la llama)
- `DELETE /api/v1/archivos/{archivo_id}` (204; 403 si no es suyo; 409 si algún escenario la usa)

Los archivos se leen en `GET /media/escenarios/<uuid>.<png|jpg>` (fuera de `/api/v1`).

Generación de imágenes con IA (Fase 15; mismo permiso `CREAR_CASOS`):

- `GET /api/v1/archivos/generacion`: `{disponible, motivo, max_por_hora, restantes, largo_max_prompt, tamanos}`.
  Sirve para activar o no el botón y mostrar cuántas imágenes le quedan al docente esta hora.
- `POST /api/v1/archivos/generar` → 201 con el mismo formato que la subida. Cuerpo:
  `{"caso_id": "...", "escenario_id": "...", "prompt": "1 a 500 caracteres", "tamano": "1536x1024"}`;
  `tamano` es `1024x1024`, `1536x1024` (por defecto) o `1024x1536`. Solo el docente dueño, con el caso en
  borrador.

| Código | Cuándo |
|---|---|
| 401 / 403 / 404 / 409 | sin sesión o permiso / no es dueño del caso / escenario inexistente / caso no borrador |
| 422 | prompt vacío o de más de 500, tamaño no permitido, o `PROMPT_RECHAZADO` (el proveedor bloqueó el contenido) |
| 429 | `LIMITE_GENERACION_ALCANZADO` (tope por hora; dice a qué hora de Bogotá puede volver a intentar) o `PROVEEDOR_IMAGENES_SATURADO` |
| 409 | `GENERACION_EN_CURSO` (ya tiene una generándose) |
| 502 | el proveedor falló, su respuesta no es una imagen JPG/PNG válida, o la clave/modelo están mal configurados |
| 503 | `GENERACION_NO_DISPONIBLE`: función desactivada o falta la clave |
| 504 | `GENERACION_TIEMPO_AGOTADO` |

Los archivos de `GET /archivos` y `POST /archivos/*` traen `origen` (`SUBIDO` o `GENERADO_IA`) y, si fue
generado, `prompt_generacion`.

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

## Interfaz web (fuera de `/api/v1`, no aparece en Swagger)

- `GET /` redirige a `/app/`.
- `GET /app/` (ingreso), `/app/registro`, `/app/docente`, `/app/simulador` y `/app/resultado`: páginas HTML.
- `GET /app/static/*`: CSS y JS de la interfaz.
- `GET /media/*`: imágenes subidas por los docentes para el editor visual de escenarios.
