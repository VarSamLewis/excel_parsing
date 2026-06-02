# ingest-fresh

Local-first Excel ingestion system with a FastAPI backend and Typer CLI.

Given an Excel file and a target schema, it can:

- infer mappings,
- extract structured rows,
- generate runnable Python ingestion code,
- optionally verify generated output,
- and log run/LLM metadata to SQLite for local analysis.

## Codebase Evaluation

Current state is strong for local demos and iteration:

- **Clear backend/CLI split**: business logic is centered in `backend/main.py` and reusable from CLI.
- **Good local observability**: structured stdout logs plus SQLite metadata logs in `backend/data/ingest_logs.db`.
- **Useful verification flow**: deterministic prechecks + optional LLM narrative for anomaly cases.
- **Practical artifacts**: `ingest_<excelname>.py`, `ingest_<excelname>.json`, optional `verification_report.md` are demo-friendly.

Notable cleanup opportunities:

- `docs/testing-and-deployment.md` and `docs/technical-approach.md` contain outdated references (cache/old outputs).
- Runtime artifacts are currently tracked in git in this repo state (`uploads/`, sqlite db, generated files); add/adjust `.gitignore` as needed.

## Architecture

- Backend: FastAPI (`backend/`)
- CLI: Typer (`cli/excel_ingest_cli.py`)
- LLM: OpenAI API (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`)
- Local state:
  - Schemas: `backend/data/local_schemas.json`
  - Logs: `backend/data/ingest_logs.db`
  - Uploads: `uploads/`

## Requirements

- Python 3.12+
- `uv` recommended (or `pip`)
- OpenAI API key (or compatible endpoint)

## Quickstart

1) Install dependencies

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pip install -r cli/requirements.txt
```

2) Configure environment

```bash
cp .env.example backend/.env
```

Set at least:

```bash
OPENAI_API_KEY=your_key
```

Optional:

```bash
OPENAI_BASE_URL=
OPENAI_MODEL_MAPPER=gpt-4o
OPENAI_MODEL_VALIDATOR=gpt-4o-mini
```

3) Run backend

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

4) Generate sample test files (optional)

```bash
python3 generate_test_excels.py --out-dir ./tmp_excels
```

## CLI Usage

Show commands:

```bash
python3 cli/excel_ingest_cli.py --help
```

Health check:

```bash
python3 cli/excel_ingest_cli.py health
```

Ingest (writes `ingest_<excelname>.py` + `ingest_<excelname>.json`):

```bash
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/sales_sample.schema.json \
  --excel-file ./test_excels/sales_sample.xlsx \
  --out-dir ./artifacts/sales
```

Ingest + verification report:

```bash
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/sales_sample.schema.json \
  --excel-file ./test_excels/sales_sample.xlsx \
  --out-dir ./artifacts/sales \
  --verify
```

Ingest all `.xlsx` files in a directory:

```bash
python3 cli/excel_ingest_cli.py ingest-dir \
  --schema-file ./test_schemas/sales_sample.schema.json \
  --excel-dir ./tmp_excels \
  --out-dir ./artifacts/batch
```

Outputs in `--out-dir`:

- `ingest_<excelname>.py`
- `ingest_<excelname>.json`
- `ingest_output_<excelname>.json` (when `--verify`)
- `verification_report_<excelname>.md` (when `--verify`)

## Schema Commands

```bash
python3 cli/excel_ingest_cli.py schemas list
python3 cli/excel_ingest_cli.py schemas create --schema-file ./schema.json
python3 cli/excel_ingest_cli.py schemas update --schema-id scm_123 --schema-file ./schema.json
python3 cli/excel_ingest_cli.py schemas delete --schema-id scm_123
python3 cli/excel_ingest_cli.py schemas clear --yes
```

## Log Queries (CLI)

```bash
python3 cli/excel_ingest_cli.py logs runs --limit 20
python3 cli/excel_ingest_cli.py logs run --run-id run_abc123
python3 cli/excel_ingest_cli.py logs usage --since-hours 24
python3 cli/excel_ingest_cli.py logs runs --limit 20 --json
```

## Tests

Run e2e/API tests:

```bash
pytest backend/tests -q
```
