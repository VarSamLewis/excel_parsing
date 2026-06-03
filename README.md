# ingest-fresh

Local-first Excel ingestion system with a FastAPI backend and Typer CLI.

Given an Excel file and a target schema, it can:

- infer mappings via GPT-4o,
- extract structured rows using a deterministic transform engine,
- generate runnable Python ingestion code,
- optionally verify generated output with deterministic prechecks + LLM narrative,
- and log run/LLM metadata to SQLite for local analysis.

## Architecture

- Backend: FastAPI (`backend/`)
- CLI: Typer (`cli/excel_ingest_cli.py`)
- LLM: OpenAI API (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`)
- Local state:
  - Logs: `backend/data/ingest_logs.db`
  - Uploads: `uploads/`

## Requirements

- Python 3.12+
- `uv` recommended (or `pip`)
- OpenAI API key (or compatible endpoint)

## Quickstart

See [docs/usage.md](docs/usage.md) for full instructions.

```bash
# 1. Install dependencies
uv pip install -r backend/requirements.txt -r cli/requirements.txt

# 2. Configure environment
cp .env.example backend/.env
# Edit backend/.env and set OPENAI_API_KEY

# 3. Run backend
uv run uvicorn backend.main:app --reload --port 8080

# 4. Run ingest (in another terminal)
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

## CLI Commands

| Command | Description |
|---|---|
| `health` | Check backend is running |
| `ingest` | Ingest one Excel file |
| `ingest-dir` | Ingest all `.xlsx` files in a directory |
| `logs runs` | List recent run IDs |
| `logs run` | Show events for one run |
| `logs usage` | Show LLM usage aggregates |

Outputs in `--out-dir`:

- `ingest_<name>.py` — generated/replay Python script
- `ingest_<name>.json` — full ingest payload
- `output_<name>.json` — output from replay script (when `--verify`)
- `verification_report_<name>.md` — quality report (when `--verify`)

## To-Do

- **Per-prompt model configurability**: Make each of the four prompt types independently configurable via separate env vars.
- **Package the project**: Replace the two `requirements.txt` files with a single `pyproject.toml`, add console-script entry points.
- **Runtime artifacts in git**: Add `.gitignore` rules for `uploads/`, sqlite db, and generated files.

## Tests

```bash
pytest backend/tests -q
```
