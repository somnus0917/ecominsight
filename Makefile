.PHONY: sync lint format typecheck test check audit warehouse analysis anomaly attribution knowledge reports evaluate evaluate-attribution evaluate-reporting demo api preview-demo frontend-install frontend-check frontend-build public-audit demo-check docker-up docker-down

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
	uv run ecom-demo

api:
	uv run ecom-api

preview-demo:
	bash scripts/preview_demo.sh

public-audit:
	uv run ecom-audit-public

demo-check:
	uv run ecom-demo
	uv run pytest tests/integration/test_demo_pipeline.py

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
