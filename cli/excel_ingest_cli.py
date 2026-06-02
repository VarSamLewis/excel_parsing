#!/usr/bin/env python3

"""CLI for the local-first ingestion backend."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(help="Excel ingestion CLI")
schemas_app = typer.Typer(help="Schema library operations")
logs_app = typer.Typer(help="Local SQLite log queries")
app.add_typer(schemas_app, name="schemas")
app.add_typer(logs_app, name="logs")

LOG_DB_PATH = Path("backend/data/ingest_logs.db")


def _log_conn() -> sqlite3.Connection:
    """Open log sqlite db; args: none; returns: sqlite3.Connection."""
    if not LOG_DB_PATH.exists():
        raise typer.BadParameter(f"Log database not found at {LOG_DB_PATH}")
    return sqlite3.connect(LOG_DB_PATH)


def _backend_url(cli_value: str | None) -> str:
    """Resolve backend URL; args: cli_value (str | None); returns: str."""
    return (
        cli_value or os.environ.get("BACKEND_URL") or "http://localhost:8080"
    ).rstrip("/")


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON object from file; args: path (Path); returns: dict[str, Any]."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise typer.BadParameter(f"Failed to parse JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise typer.BadParameter(f"Expected JSON object in {path}")
    return value


def _handle_error(exc: Exception) -> None:
    """Map HTTP exceptions to CLI exits; args: exc (Exception); returns: None."""
    if isinstance(exc, httpx.HTTPStatusError):
        body = exc.response.text
        typer.echo(f"Request failed: {exc.response.status_code} {body}", err=True)
        raise typer.Exit(1)
    if isinstance(exc, httpx.HTTPError):
        typer.echo(f"HTTP error: {exc}", err=True)
        raise typer.Exit(1)
    raise exc


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON payload to disk; args: path (Path), payload (Any); returns: None."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _default_replay_script(
    *, backend_url: str, schema_path: Path, excel_path: Path
) -> str:
    """Build fallback replay script; args: backend_url (str), schema_path (Path), excel_path (Path); returns: str."""
    return f"""#!/usr/bin/env python3
import json
from pathlib import Path

import httpx

BACKEND_URL = {backend_url!r}
SCHEMA_PATH = Path({str(schema_path)!r})
EXCEL_PATH = Path({str(excel_path)!r})
OUT_PATH = Path("ingest_output.json")


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    params = {{
        "schema_name": schema["name"],
        "schema_json": json.dumps(schema),
    }}
    files = {{
        "file": (
            EXCEL_PATH.name,
            EXCEL_PATH.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }}
    with httpx.Client(timeout=600.0) as client:
        resp = client.post(f"{{BACKEND_URL}}/ingest", params=params, files=files)
        resp.raise_for_status()
        payload = resp.json()
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {{OUT_PATH}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


@app.command("health")
def health(
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Check backend health."""
    base = _backend_url(backend_url)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{base}/health")
            resp.raise_for_status()
            typer.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        _handle_error(exc)


@schemas_app.command("list")
def schemas_list(
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """List saved schemas."""
    base = _backend_url(backend_url)
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(f"{base}/schemas")
            resp.raise_for_status()
            typer.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        _handle_error(exc)


@schemas_app.command("create")
def schemas_create(
    schema_file: Path = typer.Option(..., exists=True, dir_okay=False),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Create schema from JSON file."""
    payload = _load_json(schema_file)
    base = _backend_url(backend_url)
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{base}/schemas", json=payload)
            resp.raise_for_status()
            typer.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        _handle_error(exc)


@schemas_app.command("update")
def schemas_update(
    schema_id: str = typer.Option(..., help="Schema ID"),
    schema_file: Path = typer.Option(..., exists=True, dir_okay=False),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Update existing schema by ID."""
    payload = _load_json(schema_file)
    base = _backend_url(backend_url)
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.put(f"{base}/schemas/{schema_id}", json=payload)
            resp.raise_for_status()
            typer.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        _handle_error(exc)


@schemas_app.command("delete")
def schemas_delete(
    schema_id: str = typer.Option(..., help="Schema ID"),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Delete schema by ID."""
    base = _backend_url(backend_url)
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.delete(f"{base}/schemas/{schema_id}")
            resp.raise_for_status()
            typer.echo(json.dumps(resp.json(), indent=2))
    except Exception as exc:
        _handle_error(exc)


@schemas_app.command("clear")
def schemas_clear(
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Delete all schemas without confirmation prompt",
    ),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Delete all schemas for the current local user."""
    base: str = _backend_url(backend_url)
    if not yes:
        confirmed: bool = typer.confirm(
            "Delete all schemas for the current user?",
            default=False,
        )
        if not confirmed:
            typer.echo("Aborted.")
            return

    try:
        with httpx.Client(timeout=60.0) as client:
            list_resp: httpx.Response = client.get(f"{base}/schemas")
            list_resp.raise_for_status()
            payload: dict[str, Any] = list_resp.json()
            schemas_raw: object = payload.get("schemas", [])
            schemas: list[dict[str, Any]] = (
                schemas_raw if isinstance(schemas_raw, list) else []
            )

            schema_ids: list[str] = []
            entry: dict[str, Any]
            for entry in schemas:
                schema_id: object = entry.get("id")
                if isinstance(schema_id, str) and schema_id:
                    schema_ids.append(schema_id)

            if not schema_ids:
                typer.echo("No schemas to delete.")
                return

            deleted_count: int = 0
            sid: str
            for sid in schema_ids:
                delete_resp: httpx.Response = client.delete(f"{base}/schemas/{sid}")
                delete_resp.raise_for_status()
                deleted_count += 1

        typer.echo(f"Deleted {deleted_count} schemas.")
    except Exception as exc:
        _handle_error(exc)


@logs_app.command("runs")
def logs_runs(limit: int = typer.Option(20, help="Max runs to show")) -> None:
    """List recent run IDs; args: limit (int); returns: None."""
    con: sqlite3.Connection = _log_conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        """
        SELECT run_id, MIN(created_at), MAX(created_at), COUNT(*)
        FROM events
        WHERE run_id IS NOT NULL AND run_id != ''
        GROUP BY run_id
        ORDER BY MAX(id) DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows: list[tuple[object, ...]] = cur.fetchall()
    con.close()
    for row in rows:
        run_id, started_at, ended_at, count = row
        typer.echo(f"{run_id} start={started_at} end={ended_at} events={count}")


@logs_app.command("run")
def logs_run(run_id: str = typer.Option(..., help="Run ID")) -> None:
    """Show events for one run; args: run_id (str); returns: None."""
    con: sqlite3.Connection = _log_conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        "SELECT created_at, level, event, duration_ms FROM events WHERE run_id = ? ORDER BY id",
        (run_id,),
    )
    rows: list[tuple[object, ...]] = cur.fetchall()
    con.close()
    for row in rows:
        created_at, level, event, duration_ms = row
        typer.echo(f"{created_at} {level} {event} duration_ms={duration_ms}")


@logs_app.command("usage")
def logs_usage(since_hours: int = typer.Option(24, help="Window in hours")) -> None:
    """Show llm usage aggregates; args: since_hours (int); returns: None."""
    con: sqlite3.Connection = _log_conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        """
        SELECT step, COUNT(*), COALESCE(SUM(total_tokens), 0), COALESCE(AVG(latency_ms), 0)
        FROM llm_usage
        WHERE created_at >= datetime('now', ?)
        GROUP BY step
        ORDER BY 3 DESC
        """,
        (f"-{since_hours} hours",),
    )
    rows: list[tuple[object, ...]] = cur.fetchall()
    con.close()
    for row in rows:
        step, calls, total_tokens, avg_ms = row
        avg_latency: float = float(avg_ms) if isinstance(avg_ms, (int, float)) else 0.0
        typer.echo(
            f"step={step} calls={calls} total_tokens={total_tokens} avg_latency_ms={avg_latency:.2f}"
        )


@app.command("excel-schema")
def excel_schema(
    excel_file: Path = typer.Option(..., exists=True, dir_okay=False),
    selected_sheets: str | None = typer.Option(
        None, help="Comma-separated sheet names (default all sheets)"
    ),
    out: Path = typer.Option(
        Path("./artifacts/excel_schema.json"), help="Output JSON path"
    ),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Request normalized workbook schema from backend."""
    base = _backend_url(backend_url)
    params: dict[str, str] = {}
    if selected_sheets:
        params["selected_sheets"] = selected_sheets

    files = {
        "file": (
            excel_file.name,
            excel_file.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{base}/excel-schema", params=params, files=files)
            resp.raise_for_status()
            payload = resp.json()
        _write_json(out, payload)
        typer.echo(f"Wrote {out}")
        typer.echo(
            f"excel_hash={payload.get('excel_hash')} excel_schema_hash={payload.get('excel_schema_hash')}"
        )
    except Exception as exc:
        _handle_error(exc)


@app.command("ingest")
def ingest(
    schema_file: Path = typer.Option(..., exists=True, dir_okay=False),
    excel_file: Path = typer.Option(..., exists=True, dir_okay=False),
    selected_sheets: str | None = typer.Option(
        None, help="Comma-separated sheet names (default all sheets)"
    ),
    out_dir: Path = typer.Option(Path("./artifacts"), help="Artifact output directory"),
    verify: bool = typer.Option(
        False,
        help="Run generated script and request verification markdown report",
    ),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Run backend ingestion and write JSON artifacts."""
    schema_payload = _load_json(schema_file)
    schema_name = schema_payload.get("name")
    if not isinstance(schema_name, str) or not schema_name:
        raise typer.BadParameter("Schema file must include non-empty top-level 'name'")

    base = _backend_url(backend_url)
    params = {
        "schema_name": schema_name,
        "schema_json": json.dumps(schema_payload),
    }
    if selected_sheets:
        params["selected_sheets"] = selected_sheets

    files = {
        "file": (
            excel_file.name,
            excel_file.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    try:
        with httpx.Client(timeout=600.0) as client:
            resp = client.post(f"{base}/ingest", params=params, files=files)
            resp.raise_for_status()
            ingest_payload = resp.json()
    except Exception as exc:
        _handle_error(exc)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    replay_out = out_dir / "run_ingest.py"

    ingest_out = out_dir / "ingest_output.json"
    _write_json(ingest_out, ingest_payload)
    replay_code = ingest_payload.get("replay_code")
    script_body = (
        replay_code
        if isinstance(replay_code, str) and replay_code.strip()
        else _default_replay_script(
            backend_url=base,
            schema_path=schema_file.resolve(),
            excel_path=excel_file.resolve(),
        )
    )
    replay_out.write_text(script_body, encoding="utf-8")

    if verify:
        verify_input: Path = out_dir / "input.xlsx"
        verify_output: Path = out_dir / "ingest_output.json"
        verify_report: Path = out_dir / "verification_report.md"
        verify_input.write_bytes(excel_file.read_bytes())
        try:
            subprocess.run(
                ["python3", str(replay_out.name)],
                cwd=str(out_dir),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise typer.BadParameter(f"Verification run failed: {exc.stderr}") from exc

        output_payload: str = verify_output.read_text(encoding="utf-8")
        try:
            with httpx.Client(timeout=180.0) as client:
                verify_resp = client.post(
                    f"{base}/verify-ingestion",
                    params={
                        "schema_json": json.dumps(schema_payload),
                        "generated_code": script_body,
                        "output_json": output_payload,
                        "run_id": str(ingest_payload.get("run_id", "")),
                    },
                )
                verify_resp.raise_for_status()
                verify_payload: dict[str, Any] = verify_resp.json()
        except Exception as exc:
            _handle_error(exc)
            return

        report_text: object = verify_payload.get("report_markdown", "")
        verify_report.write_text(str(report_text), encoding="utf-8")
        typer.echo(f"Wrote {verify_report}")

    row_count = ingest_payload.get("row_count")
    sheets = ingest_payload.get("sheet_names")
    validation_raw = ingest_payload.get("validation")
    validation = validation_raw if isinstance(validation_raw, dict) else {}
    confidence = validation.get("confidence")
    issues_raw = validation.get("issues")
    issues = issues_raw if isinstance(issues_raw, list) else []
    confidence_str = (
        f"{float(confidence):.3f}" if isinstance(confidence, (int, float)) else "n/a"
    )

    typer.echo(
        f"Ingest OK: rows={row_count} sheets={sheets} confidence={confidence_str} issues={len(issues)}"
    )
    typer.echo(f"Wrote {replay_out}")
    typer.echo(f"Wrote {ingest_out}")


if __name__ == "__main__":
    app()
