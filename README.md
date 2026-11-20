# Inter Nos

Backend FastAPI del simulador de casos academicos de Psicologia Social.

## Requisitos

- Python 3.12
- Docker Desktop con Docker Compose
- MySQL 8 para pruebas

## Levantar los servicios

```powershell
docker compose up -d db db-test mailpit
```

Las bases disponibles son:

- Desarrollo: `inter_nos` en `localhost:3306`
- Pruebas: `inter_nos_test` en `localhost:3307`
- Mailpit SMTP: `localhost:1025`
- Mailpit Web: `http://localhost:8025`

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
