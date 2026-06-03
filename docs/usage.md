# ingest-fresh Usage Guide

## Installation

### Dependencies

```bash
uv pip install -r backend/requirements.txt -r cli/requirements.txt
```

Or with pip:

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pip install -r cli/requirements.txt
```

### Configuration

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

## Running the Backend

```bash
uv run uvicorn backend.main:app --reload --port 8080
```

Or with pip-installed uvicorn:

```bash
python3 -m uvicorn backend.main:app --reload --port 8080
```

Health check:

```bash
python3 cli/excel_ingest_cli.py health
```

## Schema Format

Schemas are JSON files. Example (`test_schemas/people_sample.schema.json`):

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
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people
```

This produces:

- `artifacts/people/ingest_people_sample.py` — replay script
- `artifacts/people/ingest_people_sample.json` — full ingest payload

### With Verification

```bash
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/people_sample.schema.json \
  --excel-file ./test_excels/people_sample.xlsx \
  --out-dir ./artifacts/people \
  --verify
```

With `--verify`, the CLI:

1. Runs `ingest_people_sample.py` as a subprocess (replays the API call)
2. Sends the produced output to `POST /verify-ingestion`
3. Writes `verification_report_people_sample.md` with:
   - **Deterministic precheck**: null rates, type mismatch rates per field
   - **LLM narrative** (only if precheck finds issues): GPT-4o-mini analyses the output

### With a Code Template

```bash
python3 cli/excel_ingest_cli.py ingest \
  --schema-file ./test_schemas/sales_sample.schema.json \
  --excel-file ./test_excels/sales_sample.xlsx \
  --out-dir ./artifacts/sales \
  --code-template ./template.py
```

The code template guides the LLM's generated script structure. See `template.py` for an example.

## Batch Ingestion

Process all `.xlsx` files in a directory:

```bash
python3 cli/excel_ingest_cli.py ingest-dir \
  --schema-file ./test_schemas/sales_sample.schema.json \
  --excel-dir ./test_excels \
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
  └────────────────┘
        │
        ▼
  ┌─ Verification ──┐   Deterministic precheck + optional LLM narrative
  └────────────────┘
```

## Understanding the Outputs

| File | Contents |
|---|---|
| `ingest_<name>.json` | Full API response: mapping, extracted rows, validation result, lineage, replay code |
| `ingest_<name>.py` | Standalone Python script to re-run the ingest |
| `output_<name>.json` | JSON output produced by running the replay script (only with `--verify`) |
| `verification_report_<name>.md` | Quality report: field stats, anomalies, LLM narrative (only with `--verify`) |

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
python3 cli/excel_ingest_cli.py logs runs --limit 20

# Show events for a specific run
python3 cli/excel_ingest_cli.py logs run --run-id run_abc123

# Show LLM usage aggregates (last 24h)
python3 cli/excel_ingest_cli.py logs usage --since-hours 24

# JSON output
python3 cli/excel_ingest_cli.py logs runs --limit 20 --json
```

## Generating Sample Test Files

```bash
python3 generate_test_excels.py --out-dir ./tmp_excels
```
