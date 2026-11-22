# Inter Nos

Backend FastAPI del simulador de casos academicos de Psicologia Social.

## Requisitos

- Python 3.12
- Docker Desktop con Docker Compose
- MySQL 8 para pruebas

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

## Ejecutar la API

```powershell
uvicorn app.main:app --reload
```

Documentacion: `http://localhost:8000/docs`

## Pruebas y calidad

```powershell
python -m pytest
ruff check .
ruff format --check .
```
