"""All prompt strings — single source of truth for LLM interactions.

Prompts are plain strings with {placeholders} for .format() substitution.
No LLM calls happen here.
"""

from typing import cast

# ── Mapper (GPT-4o) ────────────────────────────────────────────────

MAPPER_SYSTEM_PROMPT = """\
You are an expert at analysing Excel spreadsheet structures. Your job is to \
examine a column-level summary of an Excel sheet and determine how its columns \
map to a user-defined schema.

You MUST respond with valid JSON matching the ExcelMapping schema exactly. \
Do not include any text outside the JSON object.

Rules:
1. Use the provided header row and data start row from the summary.
2. For each schema field, find the best matching column based on the column \
   header, sample values, data types, and the user's field description.
3. Choose exactly one transform per mapping from this set:
   identity | strip | to_date | to_number | to_boolean | to_string | \
   split_comma | to_integer | regex_extract | concat | conditional | \
   uppercase | lowercase | default_value | trim_whitespace | substring
   You CANNOT invent new transforms.
4. For parameterised transforms (regex_extract, concat, conditional, \
   default_value, substring), include a "transform_params" object with the \
   required parameters (see the schema below).
5. If a required field has no plausible column match, still include a mapping \
   with your best guess and explain in the "notes" field.
6. The "reasoning" field should briefly explain your overall logic.
"""

MAPPER_USER_PROMPT = """\
## Schema to extract

Name: {schema_name}

Fields:
{fields_text}

## Excel sheet summary

Sheet: "{sheet_name}"
Estimated rows: {total_rows}
Header row: {header_row}
Data start row: {data_start_row}

### Column summaries

{column_summaries_text}

---

Return a JSON object with this exact structure:
{{
  "sheet_name": "<sheet name>",
  "header_row": {header_row},
  "data_start_row": {data_start_row},
  "mappings": [
    {{
      "source_col": "<column letter>",
      "target_field": "<schema field name>",
      "transform": "<transform name from the allowed set>",
      "transform_params": {{}},
      "notes": "<why you chose this column>"
    }}
  ],
  "reasoning": "<brief overall explanation>"
}}
"""


# ── Validator (GPT-4o-mini) ─────────────────────────────────────────

VALIDATOR_SYSTEM_PROMPT = """\
You are a data quality reviewer. You will receive a sample of extracted data \
rows and the schema they were extracted against. Your job is to sense-check \
the data and report any issues.

You MUST respond with valid JSON matching the ValidationResult schema exactly. \
Do not include any text outside the JSON object.

Rules:
1. Check that values match the expected field types.
2. Look for obviously wrong mappings (e.g. dates in a "company name" field).
3. Flag empty required fields.
4. Assign a confidence score from 0.0 to 1.0.
5. Set "passed" to true if confidence >= 0.70, false otherwise.
6. List specific issues with field name, description, severity, and example rows.
7. Do NOT flag date values as being in the future or past — date validation is handled separately.
"""

VALIDATOR_USER_PROMPT = """\
## Schema

Fields:
{fields_text}

## Extracted data sample ({row_count} rows)

{data_text}

---

Return a JSON object with this exact structure:
{{
  "confidence": <float 0.0-1.0>,
  "passed": <true if confidence >= 0.70>,
  "issues": [
    {{
      "field": "<field name>",
      "issue": "<description of the problem>",
      "severity": "<warning or error>",
      "row_examples": [<row numbers>]
    }}
  ],
  "rows_sampled": {row_count},
  "summary": "<one-line summary>"
}}
"""

VERIFY_SYSTEM_PROMPT = """\
You are a data ingestion QA reviewer adding commentary to a deterministic \
precheck report. The precheck has already checked null rates, type mismatches, \
and future dates. Do NOT repeat those checks.

Your job is to review the schema, generated code, output data, and precheck \
report, then add high-level contextual commentary. Focus on patterns, edge \
cases, data quality risks, or suggestions the deterministic checks might miss.

Return markdown only — a short paragraph or bullet points. Do not include \
headings like "## LLM Commentary" or "## Summary" — just the commentary text.
"""

VERIFY_USER_PROMPT = """\
## Target schema
{schema_text}

## Generated code (truncated)
{code_text}

## Produced output sample
{output_text}

## Deterministic Precheck Report
{precheck_report}

Add contextual commentary on data quality, edge cases, or risks \
not covered by the deterministic checks above.
"""


CODEGEN_SYSTEM_PROMPT = """\
You are an expert Python data engineer.

Generate a complete runnable Python script that ingests an Excel file into rows
matching a provided target schema.

Hard requirements:
1. Use openpyxl (not pandas).
2. Input must be read from EXCEL_PATH.
3. Output must be a JSON file written to OUT_PATH.
4. Output JSON must be a list[dict], where keys are target schema field names.
5. Use reasonable column-to-field matching based on sheet summaries.
6. Include helper functions in the generated code for type conversions.
7. Generated script must be deterministic and runnable as-is.
8. Return ONLY Python code, no markdown fences and no explanation.
"""


CODEGEN_USER_PROMPT = """\
## Target schema

Name: {schema_name}

Fields:
{fields_text}

## Sheet summary

{sheet_summary_text}

## Required generated script interface

- Define `EXCEL_PATH = Path("input.xlsx")`
- Define `OUT_PATH = Path("ingest_output.json")`
- Define a `main() -> int` function
- On success write JSON output and print `Wrote {{OUT_PATH}}`
- Include `if __name__ == "__main__": main()`
"""


def format_fields_for_prompt(fields: list[dict[str, object]]) -> str:
    """Format schema fields for prompt text; args: fields (list[dict[str, object]]); returns: str."""
    lines: list[str] = []
    field: dict[str, object]
    for field in fields:
        req: str = "required" if bool(field.get("required", True)) else "optional"
        desc: str = str(field.get("description", ""))
        desc_part: str = f' — "{desc}"' if desc else ""
        lines.append(f"- {field['name']} ({field['field_type']}, {req}){desc_part}")
    return "\n".join(lines)


def format_column_summary(column: dict[str, object]) -> str:
    """Format one column summary block; args: column (dict[str, object]); returns: str."""
    lines: list[str] = [
        f"**Column {column['column_letter']}** — Header: {column['header'] or '(none)'}"
    ]
    lines.append(f"  Non-empty cells: {column['non_empty_count']}")

    if column.get("dominant_type"):
        lines.append(f"  Dominant type: {column['dominant_type']}")

    if column.get("type_inconsistencies"):
        lines.append(f"  Type issues: {column['type_inconsistencies']}")

    if column.get("first_values"):
        lines.append(f"  First values: {column['first_values']}")

    if column.get("last_values"):
        lines.append(f"  Last values: {column['last_values']}")

    if column.get("distinct_values"):
        lines.append(f"  Distinct values (categorical): {column['distinct_values']}")

    return "\n".join(lines)


def format_column_summaries(columns: list[dict[str, object]]) -> str:
    """Format all column summaries; args: columns (list[dict[str, object]]); returns: str."""
    return "\n\n".join(format_column_summary(col) for col in columns)


def build_mapper_prompt(
    schema_name: str,
    fields: list[dict[str, object]],
    sheet_summary: dict[str, object],
) -> tuple[str, str]:
    """Build mapper prompts; args: schema_name (str), fields (list[dict[str, object]]), sheet_summary (dict[str, object]); returns: tuple[str, str]."""
    fields_text: str = format_fields_for_prompt(fields)

    columns_raw: object = sheet_summary["columns"]
    columns: list[dict[str, object]] = cast(list[dict[str, object]], columns_raw)
    column_summaries_text: str = format_column_summaries(columns)
    user_prompt: str = MAPPER_USER_PROMPT.format(
        schema_name=schema_name,
        fields_text=fields_text,
        sheet_name=sheet_summary["sheet_name"],
        total_rows=sheet_summary["total_rows"],
        header_row=sheet_summary.get("header_row", 1),
        data_start_row=sheet_summary.get("data_start_row", 2),
        column_summaries_text=column_summaries_text,
    )

    return MAPPER_SYSTEM_PROMPT, user_prompt


def build_validator_prompt(
    fields: list[dict[str, object]],
    data_sample: list[dict[str, object]],
) -> tuple[str, str]:
    """Build validator prompts; args: fields (list[dict[str, object]]), data_sample (list[dict[str, object]]); returns: tuple[str, str]."""
    fields_text: str = format_fields_for_prompt(fields)

    # Format data rows as readable text
    data_lines: list[str] = []
    i: int
    row: dict[str, object]
    for i, row in enumerate(data_sample):
        row_parts: list[str] = [
            f"{k}: {v}" for k, v in row.items() if not k.startswith("_")
        ]
        data_lines.append(f"Row {i + 1}: {{ {', '.join(row_parts)} }}")
    data_text: str = "\n".join(data_lines)

    user_prompt: str = VALIDATOR_USER_PROMPT.format(
        fields_text=fields_text,
        row_count=len(data_sample),
        data_text=data_text,
    )

    return VALIDATOR_SYSTEM_PROMPT, user_prompt


def build_codegen_prompt(
    schema_name: str,
    fields: list[dict[str, object]],
    sheet_summary: dict[str, object],
    *,
    code_template: str | None = None,
) -> tuple[str, str]:
    """Build codegen prompts; args: schema_name (str), fields (list[dict[str, object]]), sheet_summary (dict[str, object]), code_template (str | None); returns: tuple[str, str]."""
    fields_text: str = format_fields_for_prompt(fields)
    cols_raw: object = sheet_summary.get("columns", [])
    cols: list[dict[str, object]] = cast(list[dict[str, object]], cols_raw)
    cols_text: str = format_column_summaries(cols)
    sheet_summary_text: str = (
        f"Sheet: {sheet_summary.get('sheet_name')}\n"
        f"Header row: {sheet_summary.get('header_row')}\n"
        f"Data start row: {sheet_summary.get('data_start_row')}\n"
        f"Columns:\n{cols_text}"
    )
    base_prompt: str = CODEGEN_USER_PROMPT.format(
        schema_name=schema_name,
        fields_text=fields_text,
        sheet_summary_text=sheet_summary_text,
    )
    if code_template:
        base_prompt += f"\n\n## Code structure to follow\n\nFollow this structure exactly:\n\n{code_template}"
    return CODEGEN_SYSTEM_PROMPT, base_prompt


def build_verify_prompt(
    schema_json: str, code_text: str, output_text: str, precheck_report: str = ""
) -> tuple[str, str]:
    """Build verify prompts; args: schema_json (str), code_text (str), output_text (str), precheck_report (str); returns: tuple[str, str]."""
    user_prompt: str = VERIFY_USER_PROMPT.format(
        schema_text=schema_json,
        code_text=code_text,
        output_text=output_text,
        precheck_report=precheck_report,
    )
    return VERIFY_SYSTEM_PROMPT, user_prompt
