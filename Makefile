.PHONY: up down nuke logs seed test test-frontend coverage lint format check image

up:
	docker compose up -d --build

down:
	docker compose down

nuke:
	docker compose down -v

logs:
	docker compose logs -f

seed:
	docker compose run --rm backend python -m app.seed

test:
	docker compose run --rm backend pytest -q

coverage:
	docker compose run --rm backend pytest -q --cov=app --cov-report=term-missing

lint:
	docker compose run --rm backend ruff check app tests
	docker compose run --rm backend ruff format --check app tests alembic

format:
	docker compose run --rm backend ruff format app tests alembic
	docker compose run --rm backend ruff check --fix app tests

test-frontend:
	cd frontend && npm test && npm run build

# Everything CI runs, locally.
check: lint test test-frontend

image:
	docker build -t mine-action-core .
