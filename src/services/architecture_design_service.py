"""
ArchitectureDesignService – maintains and updates the system architecture.

Applies AI-driven change suggestions to the architecture context and
notifies downstream services (ImplementationDesignService) about
affected components.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json


class ArchitectureDesignService:
    """
    Updates the architecture context based on AI suggestions and
    exposes the list of changed components for implementation design.
    """

    CONTEXT_ID = "architecture"

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    def _load(self) -> dict[str, Any]:
        if not self._ctx.context_exists(self.CONTEXT_ID):
            return {"components": [], "behaviors": []}
        data = self._ctx.read_context(self.CONTEXT_ID)
        return data.get("architecture", {"components": [], "behaviors": []})

    def _save(self, architecture: dict[str, Any]) -> None:
        self._ctx.update_context(
            self.CONTEXT_ID,
            {"architecture": architecture},
            merge=False,
        )

    def update_architecture(
        self,
        changes: list[dict[str, Any]],
    ) -> dict:
        """
        Apply architectural change suggestions to the stored architecture.

        *changes* is a list of dicts with keys ``action`` (create/update/delete)
        and ``component`` (the component dict).

        Returns the updated architecture and a list of affected component names.
        """
        arch = self._load()
        components = arch.get("components", [])
        affected: list[str] = []

        for change in changes:
            action = change.get("action")
            comp = change.get("component", {})
            name = comp.get("component", "")

            if action == "create":
                # Only add if not already present
                if not any(c["component"] == name for c in components):
                    components.append(comp)
                    affected.append(name)

            elif action == "update":
                for i, c in enumerate(components):
                    if c["component"] == name:
                        components[i] = comp
                        affected.append(name)
                        break
                else:
                    # Component didn't exist – create it
                    components.append(comp)
                    affected.append(name)

            elif action == "delete":
                new = [c for c in components if c["component"] != name]
                if len(new) < len(components):
                    affected.append(name)
                components = new

        arch["components"] = components
        self._save(arch)

        return {
            "status": "updated",
            "affected_components": affected,
            "architecture": arch,
        }

    def notify_component_changes(
        self,
        affected_components: list[str],
    ) -> list[dict[str, Any]]:
        """
        Gather full component info for each affected component name.

        Returns a list of component dicts that can be forwarded to the
        ImplementationDesignService.
        """
        arch = self._load()
        components = arch.get("components", [])
        return [c for c in components if c["component"] in affected_components]

    def get_architecture(self) -> dict[str, Any]:
        """Return the full architecture context."""
        return self._load()
