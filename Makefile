PYTHON ?= python3

.PHONY: install run-api run-bot run-worker run-beat lint test

install:
	$(PYTHON) -m pip install -e ".[dev]"

run-api:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-bot:
	$(PYTHON) -m app.bot.runner

run-worker:
	celery -A app.workers.celery_app.celery_app worker --loglevel=info

run-beat:
	celery -A app.workers.celery_app.celery_app beat --loglevel=info

lint:
	ruff check app tests

test:
	pytest

