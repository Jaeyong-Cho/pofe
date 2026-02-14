"""
ContextManager – persistent storage for project context.

All context is stored in a single SQLite database (defaults to
``context/context.db``).  Each context "type" (overview, requirements,
architecture, implementation, ideas) maps to one row keyed by its
logical name.

The module hides serialisation, database access, schema management,
and cross-layer UID traversal behind a simple interface.

UID prefixes determine the context layer:
    req-   → requirements
    arch-  → architecture (components)
    cls-   → implementation (class)
    mtd-   → implementation (method)
    fn-    → implementation (function)
"""

import json
import sqlite3
from pathlib import Path
from typing import Any


_DEFAULT_CONTEXT_DIR = "context"
_DB_FILENAME = "context.db"


class ContextManager:
    """
    CRUD operations on project context backed by SQLite, with
    cross-layer UID traversal via ``related_to`` links.

    Each *context_id* is a short logical name (e.g. ``"overview"``,
    ``"requirements"``).  Data is stored as a JSON text column in a
    single ``contexts`` table.

    Use ``find_by_uid`` to locate any item by its UID, and
    ``gather_related`` to follow ``related_to`` links across layers.
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
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS contexts ("
            "  context_id TEXT PRIMARY KEY,"
            "  data TEXT NOT NULL"
            ");"
            "CREATE TABLE IF NOT EXISTS uid_index ("
            "  uid TEXT PRIMARY KEY,"
            "  context_id TEXT NOT NULL,"
            "  data TEXT NOT NULL"
            ");"
        )
        self._conn.commit()
        self._rebuild_uid_index()

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
        self._reindex_context(context_id, data)
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
        self._reindex_context(context_id, data)
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
            "DELETE FROM uid_index WHERE context_id = ?", (context_id,)
        )
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

    # -- UID traversal --------------------------------------------------------

    def find_by_uid(self, uid: str) -> dict[str, Any] | None:
        """
        Locate a single item by its UID.

        Uses the ``uid_index`` table for O(1) lookup instead of
        scanning the full JSON blob.

        Returns the item dict (with ``uid``, ``related_to``, etc.)
        or ``None`` if not found.
        """
        row = self._conn.execute(
            "SELECT data FROM uid_index WHERE uid = ?", (uid,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def gather_related(self, uid: str, depth: int = 1) -> dict[str, Any]:
        """
        Follow ``related_to`` links starting from *uid* and assemble
        a focused cross-layer context bundle.

        Returns::

            {
                "root": <the item found by uid>,
                "related": {
                    "<uid>": <item dict>,
                    ...
                }
            }

        *depth* controls how many hops to follow (default 1).
        A depth of 0 returns only the root item.
        """
        root = self.find_by_uid(uid)
        if root is None:
            return {"root": None, "related": {}}

        related: dict[str, dict[str, Any]] = {}
        self._traverse(root, depth, related, visited={uid})

        return {"root": root, "related": related}

    def gather_related_batch(self, uids: list[str], depth: int = 1) -> dict[str, Any]:
        """
        Gather related items for multiple UIDs at once.

        Returns::

            {
                "items": {
                    "<uid>": <item dict>,
                    ...
                },
                "related": {
                    "<uid>": <item dict>,
                    ...
                }
            }
        """
        items: dict[str, dict[str, Any]] = {}
        related: dict[str, dict[str, Any]] = {}
        visited: set[str] = set()

        for uid in uids:
            item = self.find_by_uid(uid)
            if item is None:
                continue
            items[uid] = item
            visited.add(uid)

        for uid, item in items.items():
            self._traverse(item, depth, related, visited)

        # Don't include root items in related
        for uid in items:
            related.pop(uid, None)

        return {"items": items, "related": related}

    def _traverse(
        self,
        item: dict[str, Any],
        depth: int,
        collected: dict[str, dict[str, Any]],
        visited: set[str],
    ) -> None:
        """Recursively follow related_to links up to *depth* hops."""
        if depth <= 0:
            return
        for ref_uid in item.get("related_to", []):
            if ref_uid in visited:
                continue
            visited.add(ref_uid)
            ref_item = self.find_by_uid(ref_uid)
            if ref_item is not None:
                collected[ref_uid] = ref_item
                self._traverse(ref_item, depth - 1, collected, visited)

    # -- UID index maintenance ------------------------------------------------

    def _rebuild_uid_index(self) -> None:
        """Rebuild the entire uid_index from all stored contexts."""
        self._conn.execute("DELETE FROM uid_index")
        for context_id in self.list_contexts():
            try:
                data = self.read_context(context_id)
            except FileNotFoundError:
                continue
            self._reindex_context(context_id, data, commit=False)
        self._conn.commit()

    def _reindex_context(
        self,
        context_id: str,
        data: dict[str, Any],
        commit: bool = False,
    ) -> None:
        """Replace all uid_index rows for a single context."""
        self._conn.execute(
            "DELETE FROM uid_index WHERE context_id = ?", (context_id,)
        )
        for uid, item in self._extract_uid_items(context_id, data):
            self._conn.execute(
                "INSERT OR REPLACE INTO uid_index (uid, context_id, data) VALUES (?, ?, ?)",
                (uid, context_id, json.dumps(item, ensure_ascii=False)),
            )
        if commit:
            self._conn.commit()

    @staticmethod
    def _extract_uid_items(
        context_id: str,
        data: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Extract all (uid, item_dict) pairs from a context blob.

        Knows how to walk each context layer's structure.
        """
        items: list[tuple[str, dict[str, Any]]] = []

        if context_id == "requirements":
            for r in data.get("requirements", []):
                uid = r.get("uid")
                if uid:
                    items.append((uid, r))

        elif context_id == "architecture":
            arch = data.get("architecture", {})
            for c in arch.get("components", []):
                uid = c.get("uid")
                if uid:
                    items.append((uid, c))

        elif context_id == "implementation":
            for f in data.get("files", []):
                for cls in f.get("classes", []):
                    uid = cls.get("uid")
                    if uid:
                        items.append((uid, cls))
                    for mtd in cls.get("methods", []):
                        uid = mtd.get("uid")
                        if uid:
                            items.append((uid, mtd))
                for fn in f.get("functions", []):
                    uid = fn.get("uid")
                    if uid:
                        items.append((uid, fn))

        return items
