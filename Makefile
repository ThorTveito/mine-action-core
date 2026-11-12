.PHONY: up down nuke logs seed test coverage lint image

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

image:
	docker build -t mine-action-core .
