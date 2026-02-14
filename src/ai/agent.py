"""
AIAgent – intelligent context-aware query and summarisation.

Uses the ContextManager to retrieve project context and the AI model
layer to answer user queries, generate summaries, and enrich context
with new analysis data.  Runs entirely in the CLI – no server needed.

When a query targets specific entities, the agent uses ``related_to``
traversal to assemble focused cross-layer context instead of dumping
everything.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai, ask_ai_json


class AIAgent:
    """
    Provides intelligent responses to user queries using managed project context.
    """

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def answer_query(self, query: str, context_id: str | None = None) -> str:
        """
        Answer a user query using the AI model and available project context.

        If *context_id* is given, only that context is included.
        Otherwise the agent asks the AI to identify relevant UIDs, then
        follows ``related_to`` links to assemble focused context.
        Falls back to all contexts if no UIDs can be identified.
        """
        context_block = self._gather_context(context_id, query)

        prompt = f"""You are an expert software engineering assistant.
Answer the following question using the project context provided.
Be concise and specific.

<project context>
{context_block}
</project context>

<question>
{query}
</question>
"""
        return ask_ai(prompt, backend=self._backend)

    def summarize_project(self, context_id: str | None = None) -> str:
        """
        Generate a concise project summary from context data.

        Uses the overview context by default, or a specific context if provided.
        """
        if context_id:
            data = self._ctx.read_context(context_id)
        elif self._ctx.context_exists("overview"):
            data = self._ctx.read_context("overview")
        else:
            return "No project context available. Run 'understand_project' first."

        prompt = f"""You are an expert software engineering assistant.
Summarize the following project context in a clear, structured way.
Include the project's purpose, key components, and current status.

<context>
{json.dumps(data, indent=2)}
</context>
"""
        return ask_ai(prompt, backend=self._backend)

    def update_context_from_analysis(
        self,
        context_id: str,
        analysis_data: dict[str, Any],
    ) -> dict:
        """
        Merge new analysis results into an existing context.

        This allows the agent to enrich context in real time as it
        discovers new information.
        """
        return self._ctx.update_context(context_id, analysis_data, merge=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _gather_context(
        self,
        context_id: str | None = None,
        query: str | None = None,
    ) -> str:
        """
        Build a focused context block.

        Strategy:
        1. If a specific context_id is given, return that context.
        2. Otherwise, identify relevant UIDs from the query, then use
           ``gather_related`` to pull only connected items.
        3. Fall back to dumping all contexts if no UIDs can be identified.
        """
        if context_id:
            data = self._ctx.read_context(context_id)
            return json.dumps(data, indent=2)

        # Try to identify relevant UIDs from the query
        if query:
            uids = self._identify_relevant_uids(query)
            if uids:
                return self._format_related_context(uids)

        # Fallback: dump all contexts
        return self._dump_all_contexts()

    def _identify_relevant_uids(self, query: str) -> list[str]:
        """
        Match the query against known entity names to find relevant UIDs.

        Uses a lightweight name→UID index built from all context layers.
        """
        index = self._build_name_index()
        query_lower = query.lower()
        matched: list[str] = []

        for name, uid in index.items():
            if name.lower() in query_lower:
                matched.append(uid)

        return matched

    def _build_name_index(self) -> dict[str, str]:
        """Build a name → uid mapping from all context layers."""
        index: dict[str, str] = {}

        if self._ctx.context_exists("requirements"):
            data = self._ctx.read_context("requirements")
            for r in data.get("requirements", []):
                title = r.get("title", "")
                uid = r.get("uid", "")
                if title and uid:
                    index[title] = uid

        if self._ctx.context_exists("architecture"):
            data = self._ctx.read_context("architecture")
            arch = data.get("architecture", {})
            for c in arch.get("components", []):
                name = c.get("component", "")
                uid = c.get("uid", "")
                if name and uid:
                    index[name] = uid

        if self._ctx.context_exists("implementation"):
            data = self._ctx.read_context("implementation")
            for f in data.get("files", []):
                for cls in f.get("classes", []):
                    name = cls.get("name", "")
                    uid = cls.get("uid", "")
                    if name and uid:
                        index[name] = uid
                for fn in f.get("functions", []):
                    name = fn.get("name", "")
                    uid = fn.get("uid", "")
                    if name and uid:
                        index[name] = uid

        return index

    def _format_related_context(self, uids: list[str]) -> str:
        """Follow related_to links for all UIDs and format the result."""
        bundle = self._ctx.gather_related_batch(uids, depth=1)
        all_items: dict[str, dict[str, Any]] = {}
        all_items.update(bundle.get("items", {}))
        all_items.update(bundle.get("related", {}))

        if not all_items:
            return self._dump_all_contexts()

        parts: list[str] = []
        for uid, item in all_items.items():
            prefix = uid.split("-", 1)[0] if "-" in uid else "unknown"
            parts.append(f"--- {prefix}: {uid} ---\n{json.dumps(item, indent=2)}")

        return "\n\n".join(parts)

    def _dump_all_contexts(self) -> str:
        """Dump all stored contexts as a text block."""
        parts: list[str] = []
        for cid in self._ctx.list_contexts():
            try:
                data = self._ctx.read_context(cid)
                parts.append(f"--- {cid} ---\n{json.dumps(data, indent=2)}")
            except Exception:
                continue
        return "\n\n".join(parts) if parts else "(no context available)"
