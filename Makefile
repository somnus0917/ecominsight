.PHONY: sync lint format typecheck test check audit warehouse analysis anomaly attribution evaluate evaluate-attribution demo

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

evaluate:
	uv run ecom-evaluate-anomaly

evaluate-attribution:
	uv run ecom-evaluate-attribution

demo:
	uv run ecom-generate-demo-data
