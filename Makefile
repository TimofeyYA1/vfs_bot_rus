.PHONY: install bootstrap once run test lint docker-up

install:
	python -m pip install -e ".[dev]"
	playwright install chromium

bootstrap:
	python -m vfs_bot bootstrap

once:
	python -m vfs_bot once

run:
	python -m vfs_bot run

test:
	pytest -q

lint:
	ruff check .

docker-up:
	docker compose up -d --build
