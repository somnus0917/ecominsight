.PHONY: sync lint format typecheck test check audit warehouse analysis anomaly attribution knowledge reports evaluate evaluate-attribution evaluate-reporting demo api frontend-install frontend-check frontend-build docker-up docker-down

sync:
	uv sync --all-groups

lint:
	uv run ruff check src tests scripts

format:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

typecheck:
	uv run mypy src

test:
	uv run pytest

check: lint typecheck test

audit:
	uv run ecom-audit-data

warehouse:
	uv run ecom-build-warehouse

analysis:
	uv run ecom-run-analysis

anomaly:
	uv run ecom-run-anomaly

attribution:
	uv run ecom-run-attribution

knowledge:
	uv run ecom-build-knowledge

reports:
	uv run ecom-generate-reports

evaluate:
	uv run ecom-evaluate-anomaly

evaluate-attribution:
	uv run ecom-evaluate-attribution

evaluate-reporting:
	uv run ecom-evaluate-reporting

demo:
	uv run ecom-generate-demo-data

api:
	uv run ecom-api

frontend-install:
	npm --prefix frontend ci

frontend-check:
	npm --prefix frontend run check

frontend-build:
	npm --prefix frontend run build

docker-up:
	docker compose up --build

docker-down:
	docker compose down
