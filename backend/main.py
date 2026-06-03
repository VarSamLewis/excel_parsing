"""FastAPI application — routes only, no business logic."""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.models import (
    ExcelMapping,
    IngestResponse,
    SchemaDefinition,
    SheetResult,
)
from backend.excel_processor import (
    compute_file_hash,
    get_sheet_names,
)
from backend.llm.mapper import generate_ingest_code, infer_mapping
from backend.llm.validator import validate_extraction, verify_generated_output
from backend.extractor.engine import extract
from backend.file_store import LocalFileStore, get_file_store
from backend.observability import configure_logging, OperationTimer, log_event
from backend.verification import run_precheck, render_precheck_markdown

# Configure structured logging.
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Excel Ingestion API",
    version="1.0.0",
    description="Flexible Excel ingestion powered by GPT-4o mapping and deterministic extraction.",
)

# ── CORS ────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared state ────────────────────────────────────────────────────

_file_store: LocalFileStore | None = None


def _get_file_store() -> LocalFileStore:
    """Get file-store singleton; args: none; returns: LocalFileStore."""
    global _file_store
    if _file_store is None:
        _file_store = get_file_store()
    return _file_store


# ── Auth dependency ─────────────────────────────────────────────────


async def get_user(request: Request) -> dict[str, str]:
    """Return local stub user; args: request (Request); returns: dict[str, str]."""
    _ = request
    return {"oid": "local-dev-user", "name": "Local Developer"}


# ── Health ──────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    """Return service health status; args: none; returns: dict[str, str]."""
    return {"status": "ok"}


# ── Ingestion ───────────────────────────────────────────────────────


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    request: Request,
    file: UploadFile = File(...),
    schema_name: str = Query(..., description="Schema name"),
    schema_json: str = Query(..., description="JSON-encoded schema definition"),
    code_template: str = Query(
        default="",
        description="Optional code template to guide generated script structure",
    ),
    user: dict[str, str] = Depends(get_user),
) -> IngestResponse:
    """Map + extract + validate an Excel file against a schema.

    Flow:
    1. Hash the file and store the upload
    2. Pick the first sheet in the workbook
    3. Generate replay code
    4. Infer mapping, extract, validate
    5. Return response
    """
    fstore: LocalFileStore = _get_file_store()
    file_bytes: bytes = await file.read()
    file_hash: str = compute_file_hash(file_bytes)
    run_id: str = f"run_{uuid.uuid4().hex[:12]}"
    user_id: str = user.get("oid", "local-dev-user")

    log_event(
        "ingest_started", logger, file_hash=file_hash, user_id=user_id, run_id=run_id
    )

    # Parse schema from query param
    try:
        schema_data = json.loads(schema_json)
        schema = SchemaDefinition.model_validate(schema_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid schema: {e}") from e

    schema_id = schema.id or "ephemeral"
    schema_version = getattr(schema, "version", 1)
    replay_code: str = ""

    # 1. Store the uploaded file
    try:
        storage_path = fstore.store_file(user_id, file_hash, file_bytes)
        log_event("file_stored", logger, file_hash=file_hash, user_id=user_id)
    except Exception as e:
        logger.warning("File storage failed (non-fatal): %s", e)
        storage_path = ""

    # 2. Check OpenAI is configured
    if not settings.openai_available:
        raise HTTPException(
            status_code=503,
            detail="OpenAI is not configured. Set OPENAI_API_KEY.",
        )

    # 3. Pick the first sheet
    all_sheet_names = get_sheet_names(file_bytes)
    sheet_name = all_sheet_names[0] if all_sheet_names else ""
    if not sheet_name:
        raise HTTPException(status_code=422, detail="Workbook has no sheets")

    with OperationTimer("llm_codegen", logger, schema_id=schema_id, run_id=run_id):
        try:
            replay_code = generate_ingest_code(
                file_bytes,
                schema,
                sheet_name,
                run_id=run_id,
                code_template=code_template or None,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Code generation failed: {exc}",
            ) from exc

    log_event(
        "sheet_selected",
        logger,
        sheet_name=sheet_name,
        file_hash=file_hash,
    )

    # 4. Infer mapping for the sheet
    with OperationTimer(
        "llm_mapping",
        logger,
        sheet_name=sheet_name,
        schema_id=schema_id,
        run_id=run_id,
    ):
        try:
            mapping = infer_mapping(file_bytes, schema, sheet_name=sheet_name)
        except Exception as e:
            logger.error("Mapping failed for sheet '%s': %s", sheet_name, e)
            raise HTTPException(
                status_code=500,
                detail=f"Mapping failed: {e}",
            ) from e

    # 5. Extract data from the sheet
    with OperationTimer("extraction", logger, sheet_name=sheet_name, run_id=run_id):
        try:
            data_rows, lineage = extract(file_bytes, file_hash, mapping)
        except Exception as e:
            logger.error("Extraction failed for sheet '%s': %s", sheet_name, e)
            raise HTTPException(
                status_code=500,
                detail=f"Extraction failed: {e}",
            ) from e

    # 6. Validate extraction
    with OperationTimer("llm_validation", logger, sheet_name=sheet_name, run_id=run_id):
        try:
            validation = validate_extraction(schema, data_rows, run_id=run_id)
        except Exception as e:
            logger.warning(
                "Validation failed for sheet '%s' (non-fatal): %s", sheet_name, e
            )
            validation = None

    log_event(
        "sheet_processing_completed",
        logger,
        sheet_name=sheet_name,
        row_count=len(data_rows),
        confidence=validation.confidence if validation else None,
    )

    sheet_result = SheetResult(
        sheet_name=sheet_name,
        mapping=mapping,
        validation=validation,
        data=data_rows,
        lineage=lineage,
        row_count=len(data_rows),
    )

    response = IngestResponse(
        success=True,
        excel_hash=file_hash,
        schema_id=schema_id,
        schema_version=schema_version,
        sheet_names=all_sheet_names,
        sheets=[sheet_result],
        mapping=mapping,
        validation=validation,
        data=data_rows,
        lineage=lineage,
        row_count=len(data_rows),
        file_storage_path=storage_path,
        replay_code=replay_code,
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
    )

    log_event(
        "ingest_completed",
        logger,
        file_hash=file_hash,
        schema_id=schema_id,
        schema_version=schema_version,
        row_count=len(data_rows),
        run_id=run_id,
    )

    return response


@app.post("/verify-ingestion")
async def verify_ingestion(
    schema_json: str = Query(..., description="JSON-encoded schema definition"),
    generated_code: str = Query(..., description="Generated python ingestion code"),
    output_json: str = Query(..., description="JSON output produced by generated code"),
    run_id: str = Query(default="", description="Optional run identifier"),
    user: dict[str, str] = Depends(get_user),
) -> dict[str, object]:
    """Verify generated ingestion output; args: schema_json (str), generated_code (str), output_json (str), run_id (str), user (dict[str, str]); returns: dict[str, str]."""
    _ = user
    log_event("verify_started", logger, run_id=run_id)
    try:
        schema_data: dict[str, object] = json.loads(schema_json)
        rows_raw: object = json.loads(output_json)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid verification payload JSON: {exc}"
        ) from exc
    rows: list[dict[str, object]] = rows_raw if isinstance(rows_raw, list) else []
    precheck: dict[str, object] = run_precheck(schema_data, rows)
    log_event(
        "verify_precheck_completed",
        logger,
        run_id=run_id,
        clean=precheck.get("clean", False),
    )

    llm_used: bool = False
    llm_section: str = ""
    if not bool(precheck.get("clean", False)):
        llm_used = True
        log_event("verify_llm_called", logger, run_id=run_id)
        llm_section = verify_generated_output(
            schema_json=schema_json,
            generated_code=generated_code,
            output_json=output_json,
            run_id=run_id,
        )
    report_markdown: str = render_precheck_markdown(precheck, llm_section=llm_section)
    log_event("verify_completed", logger, run_id=run_id, llm_used=llm_used)
    return {
        "report_markdown": report_markdown,
        "precheck": precheck,
        "llm_used": llm_used,
    }


# ── Extraction-only (manual override) ──────────────────────────────


@app.post("/extract", response_model=IngestResponse)
async def extract_with_file(
    file: UploadFile | None = File(default=None),
    excel_hash: str = Query(
        default="",
        description="File hash to retrieve from storage (if no file uploaded)",
    ),
    mapping_json: str = Query(..., description="JSON-encoded ExcelMapping"),
    schema_id: str = Query(default="ephemeral", description="Schema ID"),
    user: dict[str, str] = Depends(get_user),
) -> IngestResponse:
    """Re-run extraction with a user-provided mapping — no LLM call.

    The user corrects the inferred mapping in the UI and either re-uploads the file
    or provides the excel_hash to retrieve it from storage, skipping the LLM step.
    """
    fstore: LocalFileStore = _get_file_store()
    user_id: str = user.get("oid", "local-dev-user")

    # Get file bytes: from upload or from storage
    if file is not None:
        file_bytes = await file.read()
        file_hash = compute_file_hash(file_bytes)
    elif excel_hash:
        file_bytes = fstore.retrieve_file(user_id, excel_hash)
        if file_bytes is None:
            raise HTTPException(
                status_code=404,
                detail="File not found in storage. Please re-upload.",
            )
        file_hash = excel_hash
    else:
        raise HTTPException(
            status_code=400,
            detail="Either upload a file or provide excel_hash to retrieve from storage.",
        )

    try:
        mapping_data = json.loads(mapping_json)
        mapping = ExcelMapping.model_validate(mapping_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid mapping: {e}") from e

    # Extract data
    try:
        data_rows, lineage = extract(file_bytes, file_hash, mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}") from e

    response = IngestResponse(
        success=True,
        excel_hash=file_hash,
        schema_id=schema_id,
        mapping=mapping,
        validation=None,
        data=data_rows,
        lineage=lineage,
        row_count=len(data_rows),
        created_at=datetime.now(timezone.utc),
    )

    return response
