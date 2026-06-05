"""GPT-4o mapping call — takes an Excel column summary + schema → validated ExcelMapping.

The LLM returns constrained JSON; this module parses and validates it with Pydantic.
Includes retry logic: 1 initial attempt + 2 retries with exponential backoff.
"""

from __future__ import annotations

import json
import logging

from backend.config import settings
from backend.models import ExcelMapping, SchemaDefinition
from backend.llm.client import call_with_retry, get_client
from backend.llm.prompts import build_mapper_prompt, build_codegen_prompt
from backend.excel_processor import summarise_sheet
from openai import OpenAI

logger = logging.getLogger(__name__)


def infer_mapping(
    file_bytes: bytes,
    schema: SchemaDefinition,
    *,
    sheet_name: str | None = None,
) -> ExcelMapping:
    """Call GPT-4o to infer how the Excel file maps to the given schema.

    Uses the smart column summary (not raw row samples) to give the LLM
    better signal about each column's content, types, and patterns.

    Args:
        file_bytes: Raw Excel file bytes.
        schema: The user-defined schema to map against.
        sheet_name: Optional sheet to focus on (uses active sheet if None).

    Returns:
        A validated ExcelMapping object.

    Raises:
        ValueError: If the LLM response cannot be parsed into a valid ExcelMapping.
    """
    # 1. Build column summary for the sheet
    sheet_summary = summarise_sheet(file_bytes, sheet_name=sheet_name)

    # 2. Build prompts
    fields_dicts = [
        {
            "name": f.name,
            "field_type": f.field_type.value,
            "description": f.description,
            "required": f.required,
        }
        for f in schema.fields
    ]
    system_prompt, user_prompt = build_mapper_prompt(
        schema_name=schema.name,
        fields=fields_dicts,
        sheet_summary=sheet_summary,
    )

    # 3. Call GPT-4o with retry
    client = get_client()
    logger.info(
        "Calling GPT-4o mapper for schema '%s', sheet '%s'",
        schema.name,
        sheet_summary["sheet_name"],
    )

    raw_content = call_with_retry(
        client,
        step="mapping",
        model=settings.openai_model_mapper,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    logger.debug("Mapper raw response: %s", raw_content)

    # 4. Parse and validate
    try:
        raw_json = json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    try:
        mapping = ExcelMapping.model_validate(raw_json)
    except Exception as e:
        raise ValueError(f"LLM response failed schema validation: {e}") from e

    logger.info(
        "Mapping inferred: sheet=%s, header_row=%d, %d column mappings",
        mapping.sheet_name,
        mapping.header_row,
        len(mapping.mappings),
    )
    return mapping


def generate_ingest_code(
    file_bytes: bytes,
    schema: SchemaDefinition,
    sheet_name: str,
    *,
    run_id: str = "",
    code_template: str | None = None,
) -> str:
    """Generate Python ingest script; args: file_bytes (bytes), schema (SchemaDefinition), sheet_name (str), code_template (str | None); returns: str."""
    sheet_summary: dict[str, object] = summarise_sheet(file_bytes, sheet_name=sheet_name)
    fields_dicts: list[dict[str, object]] = [
        {
            "name": field.name,
            "field_type": field.field_type.value,
            "description": field.description,
            "required": field.required,
        }
        for field in schema.fields
    ]
    system_prompt: str
    user_prompt: str
    system_prompt, user_prompt = build_codegen_prompt(
        schema_name=schema.name,
        fields=fields_dicts,
        sheet_summary=sheet_summary,
        code_template=code_template,
    )
    client: OpenAI = get_client()
    raw_content: str = call_with_retry(
        client,
        step="codegen",
        run_id=run_id,
        model=settings.openai_model_mapper,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
    )
    content: str = raw_content.strip()
    if content.startswith("```"):
        content = content.removeprefix("```python").removeprefix("```")
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    return content
