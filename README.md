# ingest-excel

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

### CLI (pip install)

```bash
pip install -e .
ingest-excel health
ingest-excel ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

With LLM commentary on the verification report:

```bash
ingest-excel ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people \
  --llm-verify
```

With debug logging:

```bash
ingest-excel ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people \
  --debug
```

Or without installing:

```bash
pip install typer httpx
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people
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

## Tests

```bash
pytest backend/tests -q
```
