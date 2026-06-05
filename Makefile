.PHONY: install lint typecheck test ci

install:
	uv venv
	uv pip install .
	uv pip install -r backend/requirements.in
	uv pip install black ruff mypy pytest

lint:
	uv run black --check .
	uv run ruff check .

typecheck:
	uv run mypy cli/ backend/

test:
	uv run pytest -v --tb=short

ci: lint typecheck test
