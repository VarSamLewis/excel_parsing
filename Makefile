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
	docker compose up -d
	sleep 2
	uv run pytest -v --tb=short 
	uv run tests/accept_outputs.py
	docker compose down


ci: lint typecheck test
