# ingest-excel

[![CI](https://github.com/VarSamLewis/excel_parsing/actions/workflows/build-test-lint.yml/badge.svg)](https://github.com/VarSamLewis/excel_parsing/actions/workflows/build-test-lint.yml)

Local-first Excel ingestion system with a FastAPI backend and Typer CLI.

Given an Excel file and a target schema, it can:

- infer mappings via GPT-4o,
- extract structured rows using a deterministic transform engine,
- generate runnable Python ingestion code,
- verify output with deterministic prechecks (null rates, type mismatches, future dates),
- optionally include LLM contextual commentary on the verification report,
- and log run/LLM metadata to SQLite for local analysis.

## Architecture

- Backend: FastAPI (`backend/`)
- CLI: Typer (`cli/excel_ingest_cli.py`)
- LLM: OpenAI API (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`)
- Local state:
  - Logs: `backend/data/ingest_logs.db`
  - Uploads: `uploads/`

## Quickstart

See [docs/usage.md](docs/usage.md) for full instructions.

### Backend (Docker)

```bash
cp .env.example backend/.env
# Edit backend/.env and set OPENAI_API_KEY

docker compose up -d
```

### CLI (with uv — recommended)

```bash
uv venv
source .venv/bin/activate
uv pip install .
ingest-excel health
ingest-excel ingest \
  --schema-file ./tests/schemas/people_sample.schema.json \
  --excel-file ./tests/excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

### CLI (with pip)

```bash
pip install -e .
ingest-excel health
```

## CLI Commands

| Command | Description |
|---|---|
| `health` | Check backend is running |
| `ingest` | Ingest one Excel file (deterministic verification always runs) |
| `ingest --llm-verify` | Include LLM contextual commentary in the verification report |
| `ingest --debug` | Print structured log events to stderr after ingest |
| `ingest-dir` | Ingest all `.xlsx` files in a directory |
| `logs runs` | List recent run IDs |
| `logs run` | Show events for one run |
| `logs usage` | Show LLM usage aggregates |

Outputs in `--out-dir`:

- `extraction_code_<name>_<timestamp>.py` — generated/replay Python script
- `ingestion_report_<name>_<timestamp>.json` — ingest payload (mapping, validation, replay code; no data rows)
- `extracted_data_<name>_<timestamp>.json` — output from replay script
- `verify_report_<name>_<timestamp>.md` — deterministic quality report (with LLM commentary if `--llm-verify`)

## To-Do

- **Per-prompt model configurability**: Make each of the four prompt types independently configurable via separate env vars.
- **Runtime artifacts in git**: Add `.gitignore` rules for `uploads/`, sqlite db, and generated files.

## Development

### Prerequisites

```bash
uv venv
source .venv/bin/activate
uv pip install .
uv pip install -r backend/requirements.in
uv pip install black ruff mypy
```

### Run all checks

```bash
uv run black --check .       # formatting
uv run ruff check .          # linting
uv run mypy cli/ backend/    # type checking
uv run pytest -v --tb=short   # e2e tests (skipped without OPENAI_API_KEY)
```

### CI

The repository includes a GitHub Actions workflow (`.github/workflows/build-test-lint.yml`) that runs all four checks on every push/PR to `master`. E2E tests are automatically skipped in CI (they require `OPENAI_API_KEY` and a running backend).
