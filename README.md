# Inter Nos

Backend FastAPI del simulador de casos academicos de Psicologia Social.

## Requisitos

- Python 3.12
- Docker Desktop con Docker Compose
- MySQL 8 para pruebas

## Primeros pasos

1. Copiar la configuración de ejemplo (`.env` no se versiona):

   ```powershell
   cp .env.example .env
   ```

2. Rellenar en `.env` los secretos propios: `ADMIN_INICIAL_CONTRASENA`, `DOCENTE_PASSWORD`,
   `JWT_SECRET` y `FERNET_KEY` (los comandos para generarlos están en `.env.example`). Mientras
   valgan `CAMBIAR-EN-PRODUCCION`, el seed y el reseteo se niegan a ejecutarse.
3. Aplicar las migraciones:

   ```powershell
   alembic upgrade head
   ```

4. Crear los datos de demostración:

   ```powershell
   python scripts/seed.py
   ```

5. Reafirmar las contraseñas del administrador y de los docentes tras cambiar el `.env`
   (muestra solo `OK` / `FALLA` / `NO EXISTE`, nunca las contraseñas):

   ```powershell
   python scripts/reset_passwords.py
   ```

Más detalle sobre secretos y su rotación en `docs/DECISIONES.md` (sección «Credenciales y secretos»).

## Levantar desde cero

1. Clonar el repositorio y entrar en la carpeta.
2. Copiar `.env.example` a `.env` y revisar secretos.
3. Levantar servicios:

```powershell
make up
```

4. Ejecutar migraciones:

```powershell
make migrate
```

5. Crear datos de demostración:

```powershell
make seed
```

Con sesión demostrativa:

```powershell
docker compose run --rm api python scripts/seed.py --con-sesion
```

Swagger: `http://localhost:8000/docs`

## Puertos

- API: `8000`
- Desarrollo MySQL: `3308`
- Pruebas MySQL: `3307`
- Mailpit SMTP: `1025`
- Mailpit Web: `8025`

## Configuracion

```powershell
Copy-Item .env.example .env
python -m pip install -e ".[test,quality]"
```

`TEST_DATABASE_URL` debe apuntar a MySQL real. Las pruebas nunca usan SQLite.

## Migraciones

```powershell
alembic upgrade head
alembic heads
```

La migración `0012_triggers_vistas` crea 9 triggers, 1 procedimiento y 5 vistas (`vista_*`). Con el
registro binario activo, el usuario sin `SUPER` necesita `log_bin_trust_function_creators=1`: ya
viene en `docker-compose.yml`. Si tus contenedores se crearon antes, reinícialos
(`docker compose up -d db db-test`) o ejecuta una vez como root
`SET GLOBAL log_bin_trust_function_creators = 1;`. En XAMPP/MariaDB corre con `root`, que ya puede.

## Ejecutar la API

```powershell
uvicorn app.main:app --reload
```

Documentacion: `http://localhost:8000/docs`

## Interfaz web (simulador)

La misma instancia de `uvicorn` sirve la interfaz. No requiere Node ni compilar nada.

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

| Pantalla | URL |
| --- | --- |
| Ingreso (estudiante / docente / admin) | `http://localhost:8000/app/` |
| Panel del docente | `http://localhost:8000/app/docente` |
| Simulador del estudiante | `http://localhost:8000/app/simulador` |
| Puntuación final | `http://localhost:8000/app/resultado` |

Para probarlo de punta a punta: `python scripts/seed.py`, entrar como docente, agendar una sesión,
convocar a un estudiante, iniciarla, copiar el código y entrar como estudiante en otra pestaña.
Desde el celular, abre `http://<IP-de-tu-PC>:8000/app/` (misma red Wi-Fi).

El caso semilla trae 4 puzzles de ejemplo (marcados «[EJEMPLO — validar con docente]»); el docente
crea los suyos por escenario desde el editor del caso. Los puzzles no puntúan.

El docente también puede armar la imagen de cada escenario con el **editor visual de escenarios**
(botón «🎨 Crear composición» dentro del escenario, en un caso en borrador; pensado para computador).
Las imágenes que sube (JPG o PNG, máx. 5 MB) quedan en `uploads/` (ignorada por git) y se sirven en
`/media`; la carpeta se cambia con `ALMACENAMIENTO_DIR`.

### Registro con código de verificación

`/app/registro` crea la cuenta; luego pide el código de 6 dígitos enviado al correo. El docente
verificado queda `PENDIENTE` hasta que el administrador lo apruebe en la pestaña «Solicitudes».

Para ver el código en local **sin Mailpit**, en `.env` pon `EMAIL_BACKEND=console` (y
`DOMINIO_INSTITUCIONAL` con tu dominio), reinicia `uvicorn` y regístrate: el correo completo,
con el código, se imprime en la terminal de la API. Si usas el worker
(`python scripts/run_worker.py`) o `DESPACHO_INMEDIATO=false`, aparece en la terminal del worker
(hasta 10 s). Solo para desarrollo: en producción usa `EMAIL_BACKEND=smtp`.

Recuerda aplicar las migraciones nuevas (`alembic upgrade head`: `0010_registro` y
`0011_verificacion_registro`).

## Pruebas y calidad

```powershell
python -m pytest
ruff check .
ruff format --check .
```
