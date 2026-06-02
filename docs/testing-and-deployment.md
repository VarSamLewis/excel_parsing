# Testing and Local Run Guide

## Prerequisites

- Python 3.12+
- `uv` (recommended) or `pip`

## Setup

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp ../.env.example .env
```

Set at minimum:

- `OPENAI_API_KEY`

Optional:

- `OPENAI_BASE_URL` for OpenAI-compatible proxies/providers
- `OPENAI_MODEL_MAPPER` and `OPENAI_MODEL_VALIDATOR`

## Run Backend

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

## Run Tests

```bash
cd backend
uv run pytest tests/ -v
```

## CLI Smoke Checks

```bash
python3 -m pip install -r cli/requirements.txt
python3 cli/excel_ingest_cli.py health
python3 cli/excel_ingest_cli.py schemas list
python3 cli/excel_ingest_cli.py ingest --schema-file ./schema.json --excel-file ./sample.xlsx
python3 cli/excel_ingest_cli.py ingest --schema-file ./schema.json --excel-file ./sample.xlsx --verify
python3 cli/excel_ingest_cli.py logs runs --limit 10
```

`ingest` writes `artifacts/ingest_<excelname>.py` and `artifacts/ingest_<excelname>.json` by default.
