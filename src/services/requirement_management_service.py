"""
RequirementManagementService – lifecycle management for project requirements.

Manages creation, update, deletion, and categorisation of requirements.
Persists everything through the ContextManager (``requirements`` context).
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json


class RequirementManagementService:
    """
    CRUD + AI-powered categorisation for project requirements.

    Requirements are stored as a list inside the ``requirements`` context:
    ``{"requirements": [ ... ]}``.
    """

    CONTEXT_ID = "requirements"

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        """Load the current requirements list from context."""
        if not self._ctx.context_exists(self.CONTEXT_ID):
            return []
        data = self._ctx.read_context(self.CONTEXT_ID)
        return data.get("requirements", [])

    def _save(self, requirements: list[dict[str, Any]]) -> None:
        """Persist the requirements list."""
        self._ctx.update_context(
            self.CONTEXT_ID,
            {"requirements": requirements},
            merge=False,
        )

    def create_requirement(self, requirement: dict[str, Any]) -> dict:
        """
        Add a new requirement.

        *requirement* must contain at least ``title`` and ``description``.
        ``tags`` and ``status`` are optional (defaults: ``[]``, ``"new"``).
        """
        requirement.setdefault("tags", [])
        requirement.setdefault("status", "new")

        reqs = self._load()
        reqs.append(requirement)
        self._save(reqs)

        return {"title": requirement["title"], "status": "created"}

    def update_requirement(
        self,
        title: str,
        updates: dict[str, Any],
    ) -> dict:
        """
        Update the requirement matching *title*.

        Raises ``KeyError`` if no requirement with that title exists.
        """
        reqs = self._load()
        for req in reqs:
            if req["title"] == title:
                req.update(updates)
                self._save(reqs)
                return {"title": title, "status": "updated"}

        raise KeyError(f"Requirement '{title}' not found.")

    def delete_requirement(self, title: str) -> dict:
        """
        Remove the requirement matching *title*.

        Raises ``KeyError`` if not found.
        """
        reqs = self._load()
        new_reqs = [r for r in reqs if r["title"] != title]

        if len(new_reqs) == len(reqs):
            raise KeyError(f"Requirement '{title}' not found.")

        self._save(new_reqs)
        return {"title": title, "status": "deleted"}

    def get_all(self) -> list[dict[str, Any]]:
        """Return the full list of requirements."""
        return self._load()

    # ------------------------------------------------------------------
    # AI-powered categorisation
    # ------------------------------------------------------------------

    def categorize_requirements(
        self,
        requirements: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Use AI to assign or refine tags/categories on requirements.

        If *requirements* is ``None``, categorises the stored set in-place.
        """
        reqs = requirements if requirements is not None else self._load()
        if not reqs:
            return reqs

        prompt = f"""You are an expert in software engineering.

Categorize the following requirements by assigning appropriate tags.
Each requirement should have relevant, concise tags that describe its domain.

Return JSON only in this format:
{{
    "requirements": [
        {{
            "title": "...",
            "description": "...",
            "tags": ["tag1", "tag2"],
            "status": "..."
        }}
    ]
}}

Do not include any explanation or additional text.

<requirements>
{json.dumps(reqs, indent=2)}
</requirements>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        categorized = result.get("requirements", reqs)

        # Persist if we categorised the stored set
        if requirements is None:
            self._save(categorized)

        return categorized

    # ------------------------------------------------------------------
    # Bulk apply changes from AIAnalysisEngine
    # ------------------------------------------------------------------

    def apply_changes(self, changes: list[dict[str, Any]]) -> None:
        """
        Apply a batch of requirement changes (create/update/delete)
        as returned by ``AIAnalysisEngine.analyze_feature_description``.
        """
        for change in changes:
            action = change.get("action")
            req = change.get("requirement", {})

            if action == "create":
                self.create_requirement(req)
            elif action == "update":
                try:
                    self.update_requirement(req["title"], req)
                except KeyError:
                    # If it doesn't exist yet, create it
                    self.create_requirement(req)
            elif action == "delete":
                try:
                    self.delete_requirement(req["title"])
                except KeyError:
                    pass  # already gone
