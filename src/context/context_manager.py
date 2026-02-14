"""
ContextManager – persistent storage for project context.

All context is stored in a single SQLite database (defaults to
``context/context.db``).  Each context "type" (overview, requirements,
architecture, implementation, ideas) maps to one row keyed by its
logical name.

The module hides serialisation, database access, and schema management
behind a simple dict-in / dict-out interface.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any


_DEFAULT_CONTEXT_DIR = "context"
_DB_FILENAME = "context.db"


class ContextManager:
    """
    CRUD operations on project context backed by SQLite.

    Each *context_id* is a short logical name (e.g. ``"overview"``,
    ``"requirements"``).  Data is stored as a JSON text column in a
    single ``contexts`` table.
    """

    def __init__(self, context_dir: str = _DEFAULT_CONTEXT_DIR):
        self._dir = Path(context_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / _DB_FILENAME
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    # -- schema ---------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS contexts ("
            "  context_id TEXT PRIMARY KEY,"
            "  data TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    # -- public interface -----------------------------------------------------

    def create_context(self, context_id: str, data: dict[str, Any]) -> dict:
        """
        Create a new context row.

        Raises ``FileExistsError`` if a context with the same ID already
        exists – use ``update_context`` instead.
        """
        if self.context_exists(context_id):
            raise FileExistsError(
                f"Context '{context_id}' already exists. Use update_context to modify it."
            )
        self._conn.execute(
            "INSERT INTO contexts (context_id, data) VALUES (?, ?)",
            (context_id, json.dumps(data, ensure_ascii=False)),
        )
        self._conn.commit()
        return {"context_id": context_id, "status": "created"}

    def read_context(self, context_id: str) -> dict[str, Any]:
        """
        Return the full contents of an existing context.

        Raises ``FileNotFoundError`` if the context does not exist.
        """
        row = self._conn.execute(
            "SELECT data FROM contexts WHERE context_id = ?", (context_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Context '{context_id}' not found.")
        return json.loads(row[0])

    def update_context(self, context_id: str, data: dict[str, Any], merge: bool = True) -> dict:
        """
        Update (or overwrite) an existing context.

        When *merge* is ``True`` the top-level keys in *data* are merged
        into the existing dict; when ``False`` the row is replaced entirely.
        Creates the context if it does not exist yet.
        """
        if merge and self.context_exists(context_id):
            existing = self.read_context(context_id)
            existing.update(data)
            data = existing

        self._conn.execute(
            "INSERT OR REPLACE INTO contexts (context_id, data) VALUES (?, ?)",
            (context_id, json.dumps(data, ensure_ascii=False)),
        )
        self._conn.commit()
        return {"context_id": context_id, "status": "updated"}

    def remove_context(self, context_id: str) -> dict:
        """
        Delete a context row.

        Raises ``FileNotFoundError`` if the context does not exist.
        """
        if not self.context_exists(context_id):
            raise FileNotFoundError(f"Context '{context_id}' not found.")
        self._conn.execute(
            "DELETE FROM contexts WHERE context_id = ?", (context_id,)
        )
        self._conn.commit()
        return {"context_id": context_id, "status": "removed"}

    def list_contexts(self) -> list[str]:
        """Return the IDs of every stored context."""
        rows = self._conn.execute(
            "SELECT context_id FROM contexts ORDER BY context_id"
        ).fetchall()
        return [r[0] for r in rows]

    def context_exists(self, context_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM contexts WHERE context_id = ?", (context_id,)
        ).fetchone()
        return row is not None

    # -- dump to JSON ---------------------------------------------------------

    def dump_to_json(self, output_dir: str | None = None) -> list[str]:
        """
        Export every context to individual JSON files.

        Returns the list of written file paths.
        """
        out = Path(output_dir) if output_dir else self._dir
        out.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for context_id in self.list_contexts():
            data = self.read_context(context_id)
            path = out / f"{context_id}.json"
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            tmp.replace(path)
            written.append(str(path))
        return written
