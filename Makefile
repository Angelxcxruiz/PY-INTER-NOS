.PHONY: up down logs migrate seed worker test lint format

up:
	docker compose up -d --build db db-test mailpit api worker

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python scripts/seed.py

worker:
	docker compose up worker

test:
	docker compose up -d db-test
	python -m pytest -q

lint:
	ruff check .

format:
	ruff format --check .
