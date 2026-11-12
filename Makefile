.PHONY: up down nuke logs seed test

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
