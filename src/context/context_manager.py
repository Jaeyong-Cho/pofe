"""
ContextManager – persistent storage for project context.

All context is stored as JSON files under a configurable directory
(defaults to ``context/``).  Each context "type" (overview, requirements,
architecture, implementation, ideas) maps to one file.

The module hides serialisation, file-I/O, and path management behind a
simple dict-in / dict-out interface.
"""

import json
import os
from pathlib import Path
from typing import Any


# Default directory that holds every context file.
_DEFAULT_CONTEXT_DIR = "context"


class ContextManager:
    """
    CRUD operations on project-context JSON files.

    Each *context_id* is a short logical name (e.g. ``"overview"``,
    ``"requirements"``).  The backing file is
    ``<context_dir>/<context_id>.json``.
    """

    def __init__(self, context_dir: str = _DEFAULT_CONTEXT_DIR):
        self._dir = Path(context_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- helpers --------------------------------------------------------------

    def _path(self, context_id: str) -> Path:
        return self._dir / f"{context_id}.json"

    # -- public interface -----------------------------------------------------

    def create_context(self, context_id: str, data: dict[str, Any]) -> dict:
        """
        Create a new context file.

        Raises ``FileExistsError`` if a context with the same ID already
        exists – use ``update_context`` instead.
        """
        path = self._path(context_id)
        if path.exists():
            raise FileExistsError(f"Context '{context_id}' already exists. Use update_context to modify it.")

        self._write(path, data)
        return {"context_id": context_id, "status": "created"}

    def read_context(self, context_id: str) -> dict[str, Any]:
        """
        Return the full contents of an existing context.

        Raises ``FileNotFoundError`` if the context does not exist.
        """
        path = self._path(context_id)
        if not path.exists():
            raise FileNotFoundError(f"Context '{context_id}' not found.")

        return self._read(path)

    def update_context(self, context_id: str, data: dict[str, Any], merge: bool = True) -> dict:
        """
        Update (or overwrite) an existing context.

        When *merge* is ``True`` the top-level keys in *data* are merged
        into the existing dict; when ``False`` the file is replaced entirely.
        Creates the context if it does not exist yet.
        """
        path = self._path(context_id)

        if merge and path.exists():
            existing = self._read(path)
            existing.update(data)
            data = existing

        self._write(path, data)
        return {"context_id": context_id, "status": "updated"}

    def remove_context(self, context_id: str) -> dict:
        """
        Delete a context file.

        Raises ``FileNotFoundError`` if the context does not exist.
        """
        path = self._path(context_id)
        if not path.exists():
            raise FileNotFoundError(f"Context '{context_id}' not found.")

        path.unlink()
        return {"context_id": context_id, "status": "removed"}

    def list_contexts(self) -> list[str]:
        """Return the IDs of every stored context."""
        return sorted(p.stem for p in self._dir.glob("*.json"))

    def context_exists(self, context_id: str) -> bool:
        return self._path(context_id).exists()

    # -- internal I/O ---------------------------------------------------------

    def _read(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        tmp.replace(path)  # atomic on POSIX
