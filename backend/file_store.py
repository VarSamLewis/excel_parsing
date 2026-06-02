"""File storage — local filesystem.

Stores uploaded Excel files for re-processing and audit purposes.
Files are stored keyed by user ID and file hash.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_UPLOADS_DIR = Path("uploads")


class LocalFileStore:
    """Local filesystem store."""

    def __init__(self: "LocalFileStore", base_dir: Path = LOCAL_UPLOADS_DIR) -> None:
        """Initialise local file store; args: base_dir (Path); returns: None."""
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self: "LocalFileStore", user_id: str, file_hash: str) -> Path:
        """Build upload path; args: user_id (str), file_hash (str); returns: Path."""
        user_dir = self._base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{file_hash}.xlsx"

    def store_file(
        self: "LocalFileStore", user_id: str, file_hash: str, file_bytes: bytes
    ) -> str:
        """Store file bytes if missing; args: user_id (str), file_hash (str), file_bytes (bytes); returns: str."""
        path: Path = self._file_path(user_id, file_hash)
        if path.exists():
            logger.debug("File already stored locally: %s", path)
            return str(path)
        path.write_bytes(file_bytes)
        logger.info("Stored file locally: %s (%d bytes)", path, len(file_bytes))
        return str(path)

    def retrieve_file(
        self: "LocalFileStore", user_id: str, file_hash: str
    ) -> bytes | None:
        """Retrieve file bytes when available; args: user_id (str), file_hash (str); returns: bytes | None."""
        path: Path = self._file_path(user_id, file_hash)
        if not path.exists():
            return None
        return path.read_bytes()

    def file_exists(self: "LocalFileStore", user_id: str, file_hash: str) -> bool:
        """Check file existence; args: user_id (str), file_hash (str); returns: bool."""
        path: Path = self._file_path(user_id, file_hash)
        return path.exists()

    def get_storage_path(self: "LocalFileStore", user_id: str, file_hash: str) -> str:
        """Return storage path string; args: user_id (str), file_hash (str); returns: str."""
        return str(self._file_path(user_id, file_hash))


def get_file_store() -> LocalFileStore:
    """Create local file store; args: none; returns: LocalFileStore."""
    return LocalFileStore()
