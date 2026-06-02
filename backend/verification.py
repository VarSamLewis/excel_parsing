"""Deterministic verification helpers for ingestion output."""

from __future__ import annotations

from datetime import datetime, date
from typing import Any


def _is_number(value: object) -> bool:
    """Check numeric type; args: value (object); returns: bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_date_like(value: object) -> bool:
    """Check date-like value; args: value (object); returns: bool."""
    if isinstance(value, (datetime, date)):
        return True
    if isinstance(value, str):
        text: str = value.strip()
        return len(text) >= 8 and ("-" in text or "/" in text)
    return False


def _matches_type(field_type: str, value: object) -> bool:
    """Check target type match; args: field_type (str), value (object); returns: bool."""
    if value is None:
        return True
    kind: str = field_type.lower()
    if kind == "string":
        return isinstance(value, str)
    if kind == "number":
        return _is_number(value)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "date":
        return _is_date_like(value)
    return True


def run_precheck(
    schema_data: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run deterministic checks; args: schema_data (dict[str, Any]), rows (list[dict[str, Any]]); returns: dict[str, Any]."""
    fields_raw: object = schema_data.get("fields", [])
    fields: list[dict[str, Any]] = fields_raw if isinstance(fields_raw, list) else []
    row_count: int = len(rows)
    field_stats: list[dict[str, Any]] = []
    anomalies: list[str] = []

    if row_count == 0:
        anomalies.append("No rows produced")

    field: dict[str, Any]
    for field in fields:
        name: str = str(field.get("name", ""))
        kind: str = str(field.get("field_type", "string"))
        required: bool = bool(field.get("required", True))
        null_count: int = 0
        mismatch_count: int = 0
        present_count: int = 0
        row: dict[str, Any]
        for row in rows:
            value: object = row.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                null_count += 1
            else:
                present_count += 1
            if not _matches_type(kind, value):
                mismatch_count += 1

        null_rate: float = (null_count / row_count) if row_count else 1.0
        mismatch_rate: float = (mismatch_count / row_count) if row_count else 0.0
        field_stats.append(
            {
                "name": name,
                "field_type": kind,
                "required": required,
                "null_count": null_count,
                "null_rate": round(null_rate, 4),
                "present_count": present_count,
                "mismatch_count": mismatch_count,
                "mismatch_rate": round(mismatch_rate, 4),
            }
        )

        if required and null_count > 0:
            anomalies.append(
                f"Required field '{name}' has {null_count} null/empty values"
            )
        if mismatch_rate > 0.05:
            anomalies.append(
                f"Field '{name}' has high type mismatch rate ({mismatch_rate:.1%})"
            )

    clean: bool = len(anomalies) == 0
    return {
        "row_count": row_count,
        "field_stats": field_stats,
        "anomalies": anomalies,
        "clean": clean,
    }


def render_precheck_markdown(precheck: dict[str, Any], llm_section: str = "") -> str:
    """Render markdown report; args: precheck (dict[str, Any]), llm_section (str); returns: str."""
    lines: list[str] = []
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Rows produced: {precheck.get('row_count', 0)}")
    lines.append(
        f"- Deterministic status: {'PASS' if precheck.get('clean') else 'FAIL'}"
    )
    lines.append("")
    lines.append("## Numeric Diagnostics")
    lines.append("")
    lines.append("| Field | Type | Required | Null Rate | Type Mismatch Rate |")
    lines.append("|---|---|---:|---:|---:|")
    stat: dict[str, Any]
    for stat in precheck.get("field_stats", []):
        lines.append(
            f"| {stat.get('name')} | {stat.get('field_type')} | {stat.get('required')} | {float(stat.get('null_rate', 0.0)):.1%} | {float(stat.get('mismatch_rate', 0.0)):.1%} |"
        )
    lines.append("")
    lines.append("## Deterministic Findings")
    lines.append("")
    anomalies: list[str] = precheck.get("anomalies", [])
    if anomalies:
        issue: str
        for issue in anomalies:
            lines.append(f"- {issue}")
    else:
        lines.append("- No anomalies detected by deterministic checks.")

    if llm_section.strip():
        lines.append("")
        lines.append("## LLM Narrative")
        lines.append("")
        lines.append(llm_section.strip())

    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(
        "- Proceed if deterministic checks pass and no critical issues appear in LLM narrative."
    )
    return "\n".join(lines)
