# ingest-excel Usage Guide

## Installation

### Backend (Docker)

```bash
docker compose up -d
```

The backend runs on `http://localhost:8080`.

To rebuild after changes:

```bash
docker compose build
docker compose up -d
```

### CLI (pip install — recommended)

From the repo root:

```bash
pip install -e .
```

This installs the `ingest-excel` command globally (in your current venv/system):

```bash
ingest-excel --help
ingest-excel health
ingest-excel ingest \
  --schema-file ./tests/schemas/people_sample.schema.json \
  --excel-file ./tests/excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

For an isolated install:

```bash
pipx install .
```

### CLI (without installing)

Just install the two deps manually:

```bash
pip install typer httpx
python3 cli/excel_ingest_cli.py --help
```

## Configuration

```bash
cp .env.example backend/.env
```

Edit `backend/.env` and set at minimum:

```ini
OPENAI_API_KEY=sk-...
```

Optional settings:

```ini
OPENAI_MODEL_MAPPER=gpt-4o              # Model for mapping + codegen
OPENAI_MODEL_VALIDATOR=gpt-4o-mini      # Model for validation + verify
OPENAI_BASE_URL=                         # OpenAI-compatible endpoint
LOG_LEVEL=INFO
```

> If running the backend without Docker, remember to create `backend/.env` before starting uvicorn.

## Running the Backend

### With Docker (recommended)

```bash
docker compose up -d
```

View logs:

```bash
docker compose logs -f
```

### Without Docker

```bash
pip install -r backend/requirements.in
uvicorn backend.main:app --reload --port 8080
```

Health check:

```bash
ingest-excel health
# or
python3 cli/excel_ingest_cli.py health
```

## Schema Format

Schemas are JSON files. Example (`tests/schemas/people_sample.schema.json`):

```json
{
  "name": "People Sample Schema",
  "fields": [
    {
      "name": "name",
      "field_type": "string",
      "description": "Employee full name",
      "required": true
    },
    {
      "name": "start_date",
      "field_type": "date",
      "description": "Employment start date",
      "required": true
    },
    {
      "name": "salary",
      "field_type": "number",
      "description": "Annual salary",
      "required": true
    }
  ]
}
```

### Field Types

| Type | Description |
|---|---|
| `string` | Free text |
| `number` | Float/decimal |
| `integer` | Whole number |
| `boolean` | True/false |
| `date` | ISO date or parseable string |

## Ingesting a Single File

```bash
ingest-excel ingest \
  --schema-file ./tests/schemas/people_sample.schema.json \
  --excel-file ./tests/excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

This produces:

- `extraction_code_people_sample_<timestamp>.py` — replay script
- `ingestion_report_people_sample_<timestamp>.json` — ingest payload (mapping, validation, replay code; no data rows)
- `extracted_data_people_sample_<timestamp>.json` — output from replay script
- `verify_report_people_sample_<timestamp>.md` — deterministic quality report

The deterministic verification (replay script + precheck) always runs. The report is printed to stdout and saved to the file.

### With LLM Commentary

```bash
ingest-excel ingest \
  --schema-file ./tests/schemas/people_sample.schema.json \
  --excel-file ./tests/excels/people_sample.xlsx \
  --out-dir ./artifacts/people \
  --llm-verify
```

Deterministic verification (null rates, type mismatches, future dates) runs on every ingest by default — no flag needed. The `--llm-verify` flag additionally sends the deterministic report + output data to GPT-4o-mini for contextual commentary, which gets appended to the report under "## LLM Narrative".

### With Debug Logging

```bash
ingest-excel ingest \
  --schema-file ./tests/schemas/people_sample.schema.json \
  --excel-file ./tests/excels/people_sample.xlsx \
  --out-dir ./artifacts/people \
  --debug
```

Prints structured log events (timestamps, levels, event names, durations) to stderr by querying `GET /logs/{run_id}` on the backend. Useful when running against a Docker container where the log database is not directly accessible.

### With a Code Template

```bash
ingest-excel ingest \
  --schema-file ./tests/schemas/sales_sample.schema.json \
  --excel-file ./tests/excels/sales_sample.xlsx \
  --out-dir ./artifacts/sales \
  --code-template ./template.py
```

The code template guides the LLM's generated script structure. See `template.py` for an example.

## Batch Ingestion

Process all `.xlsx` files in a directory:

```bash
ingest-excel ingest-dir \
  --schema-file ./tests/schemas/sales_sample.schema.json \
  --excel-dir ./tests/excels \
  --out-dir ./artifacts/batch
```

## Pipeline Overview

```
Excel + Schema
        │
        ▼
  ┌─ LLM Codegen ──┐   Generate standalone Python extraction script
  └────────────────┘
        │
        ▼
  ┌─ LLM Mapping ───┐   GPT-4o returns ExcelMapping (column→field + transform)
  └────────────────┘
        │
        ▼
  ┌─ Deterministic ─┐   Applies transforms per mapping (no LLM)
  │  Extraction     │   Transform registry: identity, strip, to_date,
  └────────────────┘     to_number, to_boolean, to_integer, split_comma,
        │                regex_extract, concat, conditional, uppercase,
        ▼                lowercase, default_value, trim_whitespace, substring
  ┌─ LLM Validation ┐   GPT-4o-mini samples N rows, returns confidence + issues
  └────────────────┘     (prompt instructs it not to flag dates — handled separately)
        │
        ▼
  ┌─ Verification ──┐   Always runs: deterministic precheck (null rates,
  │  (deterministic)│   type mismatches, future dates) → report printed to stdout
  └────────────────┘
        │ (--llm-verify)
        ▼
  ┌─ LLM Commentary ┐   GPT-4o-mini reviews precheck report + output data,
  └────────────────┘     adds contextual commentary to the report
```

## Understanding the Outputs

| File | Contents |
|---|---|
| `ingestion_report_<name>_<timestamp>.json` | Ingest payload: mapping, validation result, lineage, replay code (data rows stripped to keep file small) |
| `extraction_code_<name>_<timestamp>.py` | Standalone Python script to re-run the ingest |
| `extracted_data_<name>_<timestamp>.json` | JSON output produced by running the replay script |
| `verify_report_<name>_<timestamp>.md` | Quality report: row count, field diagnostics, deterministic findings, and LLM commentary (if `--llm-verify`) |

The deterministic report (printed to stdout on every run) includes:

- **Summary**: row count, pass/fail status
- **Numeric Diagnostics**: per-field null rates and type mismatch rates
- **Deterministic Findings**: anomalies detected by prechecks (null required fields, type mismatches, future dates)
- **LLM Narrative** (only with `--llm-verify`): contextual commentary from GPT-4o-mini

## Transforms Reference

The LLM selects from these transforms for each column mapping:

| Transform | Description | Params |
|---|---|---|
| `identity` | Pass through unchanged | — |
| `strip` | Convert to string, strip whitespace | — |
| `to_date` | Parse to ISO date (YYYY-MM-DD) | — |
| `to_number` | Parse to float | — |
| `to_integer` | Parse to int (rounds floats) | — |
| `to_boolean` | Parse truthy/falsy values | — |
| `to_string` | Convert to string | — |
| `uppercase` | Convert to uppercase | — |
| `lowercase` | Convert to lowercase | — |
| `trim_whitespace` | Strip + collapse internal whitespace | — |
| `split_comma` | Split string by commas | — |
| `regex_extract` | Extract by regex capture group | `pattern`, `group` |
| `concat` | Concatenate with other column values | `separator`, `other_cols` |
| `conditional` | If-then-else based on value | `condition`, `compare_value`, `true_value`, `false_value` |
| `default_value` | Return default if null/empty | `default` |
| `substring` | Extract by start/end index | `start`, `end` |

## Log Queries

```bash
# List recent runs
ingest-excel logs runs --limit 20

# Show events for a specific run
ingest-excel logs run --run-id run_abc123

# Show LLM usage aggregates (last 24h)
ingest-excel logs usage --since-hours 24

# JSON output
ingest-excel logs runs --limit 20 --json
```

## Generating Sample Test Files

```bash
python3 tests/generate_test_excels.py --out-dir ./tests/excels
```

## Development

### Set up environment

```bash
make install
```

This creates a uv venv (if missing) and installs everything — the project, backend deps, and dev tools (black, ruff, mypy, pytest).

### Run all checks (same as CI pipeline)

```bash
make ci
```

Runs lint → typecheck → test in sequence, exactly like the GitHub Actions workflow.

### Individual commands

```bash
make lint       # black --check . + ruff check .
make typecheck  # mypy cli/ backend/
make test       # pytest -v --tb=short
```

### Run backend without Docker

```bash
uv run uvicorn backend.main:app --reload --port 8080
```

### Run CLI without installing

```bash
uv run python3 cli/excel_ingest_cli.py health
```

### Rebuilding Docker

```bash
docker compose build
docker compose up -d
```
