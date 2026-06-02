# Technical Approach

This project is a local-first Excel ingestion backend plus CLI.

## Architecture

- Backend: FastAPI (`backend/`) as the single source of business logic.
- CLI: Typer/httpx (`cli/`) as the client workflow.
- LLM provider: OpenAI API via `OPENAI_API_KEY` (optional `OPENAI_BASE_URL`).
- Persistence: local filesystem (`uploads/`) and local JSON schema storage (`backend/data/local_schemas.json`).

## Pipeline

1. Parse workbook and summarize sheets.
2. Use LLM to infer mapping config against the target schema.
3. Run deterministic extraction/transforms.
4. Run validation on sampled extracted rows.
5. Cache result by file hash + schema ID.

## Why Local-Only

- Lower setup overhead for development and demos.
- Fewer external infrastructure dependencies.
- Reproducible CLI/backend flow on a single machine.

## Operational Notes

- `OPENAI_BASE_URL` is optional for OpenAI-compatible endpoints.
- Logging is structured JSON to stdout.
- Auth is local stub user mode (`local-dev-user`).
