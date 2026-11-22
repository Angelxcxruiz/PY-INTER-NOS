#!/bin/sh
set -e

python - <<'PY'
import time
from sqlalchemy import text
from app.core.database import engine

for intento in range(30):
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        break
    except Exception:
        if intento == 29:
            raise
        time.sleep(2)
PY

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
