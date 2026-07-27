.PHONY: sync lint format typecheck test check audit warehouse analysis demo

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

demo:
	uv run ecom-generate-demo-data
