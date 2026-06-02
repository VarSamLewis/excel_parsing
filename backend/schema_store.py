"""Schema library — local JSON store.

Schema definitions are persisted to a JSON file at ./backend/data/local_schemas.json.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOCAL_SCHEMA_STORE_PATH = Path("backend/data/local_schemas.json")


def _now() -> str:
    """Return UTC timestamp string; args: none; returns: str."""
    return datetime.now(timezone.utc).isoformat()


class LocalSchemaStore:
    """Simple JSON file-backed schema store for local development."""

    def __init__(
        self: "LocalSchemaStore", path: Path = LOCAL_SCHEMA_STORE_PATH
    ) -> None:
        """Initialise schema store; args: path (Path); returns: None."""
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {
            "schemas": {},
            "schema_history": {},
        }
        self._load()

    def _load(self: "LocalSchemaStore") -> None:
        """Load persisted schema JSON; args: none; returns: None."""
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
                if "schema_history" not in self._data:
                    self._data["schema_history"] = {}
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read local schema store file, starting fresh")
                self._data = {"schemas": {}, "schema_history": {}}

    def _save(self: "LocalSchemaStore") -> None:
        """Persist schema JSON; args: none; returns: None."""
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    def list_schemas(self: "LocalSchemaStore", user_id: str) -> list[dict[str, Any]]:
        """List user schemas; args: user_id (str); returns: list[dict[str, Any]]."""
        return [
            schema
            for schema in self._data["schemas"].values()
            if schema.get("user_id") == user_id
        ]

    def get_schema(self: "LocalSchemaStore", schema_id: str) -> dict[str, Any] | None:
        """Get schema by id; args: schema_id (str); returns: dict[str, Any] | None."""
        return self._data["schemas"].get(schema_id)

    def get_schema_version(
        self: "LocalSchemaStore", schema_id: str, version: int
    ) -> dict[str, Any] | None:
        """Get schema version; args: schema_id (str), version (int); returns: dict[str, Any] | None."""
        history: list[dict[str, Any]] = self._data["schema_history"].get(schema_id, [])
        entry: dict[str, Any]
        for entry in history:
            if entry.get("version") == version:
                return entry
        return None

    def get_schema_history(
        self: "LocalSchemaStore", schema_id: str
    ) -> list[dict[str, Any]]:
        """Get schema history; args: schema_id (str); returns: list[dict[str, Any]]."""
        return self._data["schema_history"].get(schema_id, [])

    def _archive_schema_version(
        self: "LocalSchemaStore", schema: dict[str, Any]
    ) -> None:
        """Archive schema snapshot; args: schema (dict[str, Any]); returns: None."""
        schema_id: str = schema["id"]
        if schema_id not in self._data["schema_history"]:
            self._data["schema_history"][schema_id] = []
        self._data["schema_history"][schema_id].append(dict(schema))

    def save_schema(self: "LocalSchemaStore", schema: dict[str, Any]) -> dict[str, Any]:
        """Save schema record; args: schema (dict[str, Any]); returns: dict[str, Any]."""
        if not schema.get("id"):
            schema["id"] = f"scm_{uuid.uuid4().hex[:12]}"
        schema["version"] = schema.get("version", 1)
        schema["created_at"] = schema.get("created_at") or _now()
        schema["updated_at"] = _now()
        self._data["schemas"][schema["id"]] = schema
        self._archive_schema_version(schema)
        self._save()
        return schema

    def update_schema(
        self: "LocalSchemaStore", schema_id: str, schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update schema record; args: schema_id (str), schema (dict[str, Any]); returns: dict[str, Any] | None."""
        if schema_id not in self._data["schemas"]:
            return None
        existing: dict[str, Any] = self._data["schemas"][schema_id]
        schema["id"] = schema_id
        schema["user_id"] = existing["user_id"]
        schema["version"] = existing.get("version", 1) + 1
        schema["created_at"] = existing.get("created_at", _now())
        schema["updated_at"] = _now()
        self._data["schemas"][schema_id] = schema
        self._archive_schema_version(schema)
        self._save()
        return schema

    def delete_schema(self: "LocalSchemaStore", schema_id: str) -> bool:
        """Delete schema by id; args: schema_id (str); returns: bool."""
        if schema_id in self._data["schemas"]:
            del self._data["schemas"][schema_id]
            self._save()
            return True
        return False


def get_schema_store() -> LocalSchemaStore:
    """Create local schema store; args: none; returns: LocalSchemaStore."""
    return LocalSchemaStore()
