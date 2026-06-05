#!/usr/bin/env python3

"""CLI for the local-first ingestion backend."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(help="Excel ingestion CLI")
logs_app = typer.Typer(help="Local SQLite log queries")
app.add_typer(logs_app, name="logs")

LOG_DB_PATH = Path("backend/data/ingest_logs.db")


def _log_conn() -> sqlite3.Connection:
    """Open log sqlite db; args: none; returns: sqlite3.Connection."""
    if not LOG_DB_PATH.exists():
        raise typer.BadParameter(f"Log database not found at {LOG_DB_PATH}")
    return sqlite3.connect(LOG_DB_PATH)


def _backend_url(cli_value: str | None) -> str:
    """Resolve backend URL; args: cli_value (str | None); returns: str."""
    return (cli_value or os.environ.get("BACKEND_URL") or "http://localhost:8080").rstrip("/")


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON object from file; args: path (Path); returns: dict[str, Any]."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise typer.BadParameter(f"Failed to parse JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise typer.BadParameter(f"Expected JSON object in {path}")
    return value


def _safe_stem(path: Path) -> str:
    """Build safe filename stem; args: path (Path); returns: str."""
    stem: str = path.stem.strip().lower()
    safe: list[str] = []
    ch: str
    for ch in stem:
        if ch.isalnum() or ch in ("-", "_"):
            safe.append(ch)
        else:
            safe.append("_")
    collapsed: str = "".join(safe).strip("_")
    return collapsed or "excel"


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


def _print_debug_logs(run_id: str, backend_url: str = "") -> None:
    """Print log events for a run to stderr via API; args: run_id (str), backend_url (str); returns: None."""
    if not run_id:
        typer.echo("(no run_id)", err=True)
        return
    try:
        base = _backend_url(backend_url or None)
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{base}/logs/{run_id}")
            resp.raise_for_status()
            data = resp.json()
        events: list[dict[str, object]] = data.get("events", [])
        if not events:
            typer.echo("(no log events found)", err=True)
            return
        typer.echo("── Logs ──────────────────────", err=True)
        for ev in events:
            created_at = ev.get("created_at", "")
            level = ev.get("level", "")
            event = ev.get("event", "")
            duration_ms = ev.get("duration_ms")
            dur = f" [{duration_ms}ms]" if duration_ms else ""
            typer.echo(f"  {created_at} [{level}] {event}{dur}", err=True)
        typer.echo("──────────────────────────────", err=True)
    except Exception as e:
        typer.echo(f"(failed to fetch logs: {e})", err=True)


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON payload to disk; args: path (Path), payload (Any); returns: None."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _default_replay_script(*, backend_url: str, schema_path: Path, excel_path: Path) -> str:
    """Build fallback replay script; args: backend_url (str), schema_path (Path), excel_path (Path); returns: str."""
    return f"""#!/usr/bin/env python3
import json
from pathlib import Path

import httpx

BACKEND_URL = {backend_url!r}
SCHEMA_PATH = Path({str(schema_path)!r})
EXCEL_PATH = Path({str(excel_path)!r})
OUT_PATH = Path(f"extracted_data_{_safe_stem(excel_path)}.json")


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
    main()
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


@logs_app.command("runs")
def logs_runs(
    limit: int = typer.Option(20, help="Max runs to show"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
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
    payload: list[dict[str, object]] = []
    for row in rows:
        run_id, started_at, ended_at, count = row
        payload.append(
            {
                "run_id": run_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "event_count": count,
            }
        )
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    for item in payload:
        typer.echo(
            f"{item['run_id']} start={item['started_at']} end={item['ended_at']} events={item['event_count']}"
        )


@logs_app.command("run")
def logs_run(
    run_id: str = typer.Option(..., help="Run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show events for one run; args: run_id (str); returns: None."""
    con: sqlite3.Connection = _log_conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        "SELECT created_at, level, event, duration_ms FROM events WHERE run_id = ? ORDER BY id",
        (run_id,),
    )
    rows: list[tuple[object, ...]] = cur.fetchall()
    con.close()
    payload: list[dict[str, object]] = []
    for row in rows:
        created_at, level, event, duration_ms = row
        payload.append(
            {
                "created_at": created_at,
                "level": level,
                "event": event,
                "duration_ms": duration_ms,
            }
        )
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    for item in payload:
        typer.echo(
            f"{item['created_at']} {item['level']} {item['event']} duration_ms={item['duration_ms']}"
        )


@logs_app.command("usage")
def logs_usage(
    since_hours: int = typer.Option(24, help="Window in hours"),
    as_json: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
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
    payload: list[dict[str, object]] = []
    for row in rows:
        step, calls, total_tokens, avg_ms = row
        avg_latency: float = float(avg_ms) if isinstance(avg_ms, (int, float)) else 0.0
        payload.append(
            {
                "step": step,
                "calls": calls,
                "total_tokens": total_tokens,
                "avg_latency_ms": round(avg_latency, 2),
            }
        )
    if as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    for item in payload:
        typer.echo(
            f"step={item['step']} calls={item['calls']} total_tokens={item['total_tokens']} avg_latency_ms={item['avg_latency_ms']}"
        )


@app.command("ingest")
def ingest(
    schema_file: Path = typer.Option(..., exists=True, dir_okay=False),
    excel_file: Path = typer.Option(..., exists=True, dir_okay=False),
    out_dir: Path = typer.Option(Path("./artifacts"), help="Artifact output directory"),
    llm_verify: bool = typer.Option(
        False,
        help="Include LLM contextual commentary in the verification report",
    ),
    debug: bool = typer.Option(
        False,
        help="Print structured log events to stderr after ingest",
    ),
    code_template: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        help="Optional code template file to guide generated script structure",
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
    if code_template:
        params["code_template"] = code_template.read_text(encoding="utf-8")

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

    out_dir.mkdir(parents=True, exist_ok=True)
    excel_name: str = _safe_stem(excel_file)
    timestamp: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    replay_out = out_dir / f"extraction_code_{excel_name}_{timestamp}.py"

    ingest_out = out_dir / f"ingestion_report_{excel_name}_{timestamp}.json"
    # Strip data rows from the persisted response to keep the artifact small
    ingest_payload.pop("data", None)
    for sheet in ingest_payload.get("sheets", []):
        sheet.pop("data", None)
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
    script_body = script_body.replace(
        'EXCEL_PATH = Path("input.xlsx")',
        f"EXCEL_PATH = Path({str(excel_file.resolve())!r})",
    ).replace(
        'OUT_PATH = Path("ingest_output.json")',
        f'OUT_PATH = Path(f"extracted_data_{excel_name}_{timestamp}.json")',
    )
    replay_out.write_text(script_body, encoding="utf-8")

    # Always run deterministic verification
    verify_output: Path = out_dir / f"extracted_data_{excel_name}_{timestamp}.json"
    verify_report: Path = out_dir / f"verify_report_{excel_name}_{timestamp}.md"
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
                    "use_llm": str(llm_verify).lower(),
                    "run_id": str(ingest_payload.get("run_id", "")),
                },
            )
            verify_resp.raise_for_status()
            verify_payload: dict[str, Any] = verify_resp.json()
    except Exception as exc:
        _handle_error(exc)

    report_text: object = verify_payload.get("report_markdown", "")
    verify_report.write_text(str(report_text), encoding="utf-8")
    typer.echo(str(report_text))
    typer.echo(f"Wrote {replay_out}")
    typer.echo(f"Wrote {ingest_out}")
    typer.echo(f"Wrote {verify_report}")

    if debug:
        _print_debug_logs(str(ingest_payload.get("run_id", "")), backend_url=base)


@app.command("ingest-dir")
def ingest_dir(
    schema_file: Path = typer.Option(..., exists=True, dir_okay=False),
    excel_dir: Path = typer.Option(..., exists=True, file_okay=False),
    out_dir: Path = typer.Option(Path("./artifacts"), help="Artifact output directory"),
    llm_verify: bool = typer.Option(
        False,
        help="Include LLM contextual commentary in the verification report",
    ),
    debug: bool = typer.Option(
        False,
        help="Print structured log events to stderr after ingest",
    ),
    code_template: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        help="Optional code template file to guide generated script structure",
    ),
    backend_url: str | None = typer.Option(None, help="Backend base URL"),
) -> None:
    """Run ingest for every .xlsx in a directory."""
    files: list[Path] = sorted(excel_dir.glob("*.xlsx"))
    if not files:
        raise typer.BadParameter(f"No .xlsx files found in {excel_dir}")
    excel_path: Path
    for excel_path in files:
        typer.echo(f"Processing {excel_path.name}...")
        ingest(
            schema_file=schema_file,
            excel_file=excel_path,
            out_dir=out_dir,
            llm_verify=llm_verify,
            debug=debug,
            code_template=code_template,
            backend_url=backend_url,
        )


if __name__ == "__main__":
    app()
