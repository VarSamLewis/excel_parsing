"""Structured logging and metrics for local operation."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.config import settings
from backend.log_store import init_log_store, write_event

logger = logging.getLogger(__name__)

# ── JSON Formatter ──────────────────────────────────────────────────


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as single-line JSON for structured logging."""

    def format(self: "StructuredJsonFormatter", record: logging.LogRecord) -> str:
        """Format log record as JSON; args: record (logging.LogRecord); returns: str."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields added via logger.info("msg", extra={...})
        for key in (
            "event",
            "metrics",
            "duration_ms",
            "user_id",
            "schema_id",
            "file_hash",
            "sheet_name",
            "row_count",
            "confidence",
            "transform",
            "error_type",
        ):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


# ── Setup ───────────────────────────────────────────────────────────


def configure_logging() -> None:
    """Configure root JSON logging; args: none; returns: None."""
    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Clear any existing handlers to avoid duplicates on reload
    root_logger.handlers.clear()

    # Stdout handler with JSON formatting
    stdout_handler: logging.StreamHandler = logging.StreamHandler()
    stdout_handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(stdout_handler)

    logger.info("Structured JSON logging configured")
    init_log_store()


# ── Metrics helpers ─────────────────────────────────────────────────


class OperationTimer:
    """Context manager for timing operations and logging the duration."""

    def __init__(
        self: "OperationTimer",
        operation: str,
        log: logging.Logger | None = None,
        **extra: Any,
    ) -> None:
        """Initialise timer context; args: operation (str), log (logging.Logger | None), extra (Any); returns: None."""
        self._operation = operation
        self._log = log or logger
        self._extra = extra
        self._start: float = 0

    def __enter__(self: "OperationTimer") -> "OperationTimer":
        """Enter timer context; args: none; returns: OperationTimer."""
        self._start = time.perf_counter()
        return self

    def __exit__(
        self: "OperationTimer",
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        """Exit timer context and log duration; args: exc_type (type[BaseException] | None), exc_val (BaseException | None), exc_tb (object | None); returns: bool."""
        duration_ms: float = (time.perf_counter() - self._start) * 1000
        extra: dict[str, Any] = {
            "event": self._operation,
            "duration_ms": round(duration_ms, 2),
            **self._extra,
        }
        write_event(
            level="ERROR" if exc_type else "INFO",
            event=self._operation,
            run_id=str(extra.get("run_id", "")),
            duration_ms=round(duration_ms, 2),
            metadata=extra,
        )
        if exc_type:
            extra["error_type"] = exc_type.__name__
            self._log.error(
                "%s failed after %.1fms: %s",
                self._operation,
                duration_ms,
                exc_val,
                extra=extra,
            )
        else:
            self._log.info(
                "%s completed in %.1fms",
                self._operation,
                duration_ms,
                extra=extra,
            )
        return False  # Don't suppress exceptions


def log_event(
    event: str,
    log: logging.Logger | None = None,
    level: int = logging.INFO,
    **kwargs: Any,
) -> None:
    """Log structured event metadata; args: event (str), log (logging.Logger | None), level (int), kwargs (Any); returns: None."""
    log = log or logger
    extra: dict[str, Any] = {"event": event, **kwargs}
    log.log(level, event, extra=extra)
    write_event(
        level=logging.getLevelName(level),
        event=event,
        run_id=str(kwargs.get("run_id", "")),
        metadata=kwargs,
    )
