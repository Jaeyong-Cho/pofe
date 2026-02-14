"""
AIAgent – intelligent context-aware query and summarisation.

Uses the ContextManager to retrieve project context and the AI model
layer to answer user queries, generate summaries, and enrich context
with new analysis data.  Runs entirely in the CLI – no server needed.
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
        Otherwise all stored contexts are bundled into the prompt.
        """
        context_block = self._gather_context(context_id)

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

    def _gather_context(self, context_id: str | None = None) -> str:
        """Build a text block from one or all stored contexts."""
        if context_id:
            data = self._ctx.read_context(context_id)
            return json.dumps(data, indent=2)

        parts: list[str] = []
        for cid in self._ctx.list_contexts():
            try:
                data = self._ctx.read_context(cid)
                parts.append(f"--- {cid} ---\n{json.dumps(data, indent=2)}")
            except Exception:
                continue
        return "\n\n".join(parts) if parts else "(no context available)"
