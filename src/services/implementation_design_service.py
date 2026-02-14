"""
ImplementationDesignService – designs functions and workflows for components.

Takes component information from the ArchitectureDesignService and produces
detailed function signatures, descriptions, inputs/outputs, and processing
logic for each component.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json


class ImplementationDesignService:
    """
    Generates implementation-level function designs for architecture components
    and persists them in the ``implementation`` context.
    """

    CONTEXT_ID = "implementation"

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    def _load(self) -> list[dict[str, Any]]:
        if not self._ctx.context_exists(self.CONTEXT_ID):
            return []
        data = self._ctx.read_context(self.CONTEXT_ID)
        impl = data.get("implementation", {})
        # Handle both formats: list or {"implementation": [...]}
        if isinstance(impl, dict):
            return impl.get("implementation", [])
        return impl

    def _save(self, implementations: list[dict[str, Any]]) -> None:
        self._ctx.update_context(
            self.CONTEXT_ID,
            {"implementation": {"implementation": implementations}},
            merge=False,
        )

    def design_functions_for_component(
        self,
        component: dict[str, Any],
        architecture: dict[str, Any],
        requirements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Design detailed functions for a single component.

        Returns a file-spec dict containing the component name, file path,
        and a list of function definitions.
        """
        reqs_block = json.dumps(requirements, indent=2) if requirements else "N/A"

        prompt = f"""You are an expert in software engineering.

Design detailed functions for the following component based on the architecture
and requirements provided.  For each function, specify its name, description,
input, processing logic, and output.

Return JSON only in this format:
{{
    "files": [
        {{
            "path": "src/services/component_name.py",
            "component": "ComponentName",
            "functions": [
                {{
                    "name": "function_name",
                    "description": "What it does.",
                    "input": "What it receives.",
                    "processing": "How it works.",
                    "output": "What it returns."
                }}
            ]
        }}
    ]
}}

Do not include any explanation or additional text.

<component>
{json.dumps(component, indent=2)}
</component>

<architecture>
{json.dumps(architecture, indent=2)}
</architecture>

<requirements>
{reqs_block}
</requirements>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        file_specs = result.get("files", [])

        # Merge into stored implementations
        self._merge_file_specs(file_specs)

        return {"component": component.get("component"), "files": file_specs}

    def provide_implementation_design(self) -> list[dict[str, Any]]:
        """
        Return the full implementation design for user review.
        """
        return self._load()

    def _merge_file_specs(self, new_specs: list[dict[str, Any]]) -> None:
        """Merge new file specs into stored implementations, replacing duplicates."""
        current = self._load()

        # Build a lookup by component name for replacement
        by_component: dict[str, int] = {}
        for i, impl_group in enumerate(current):
            files = impl_group.get("files", [])
            for f in files:
                by_component[f.get("component", "")] = i

        # For simplicity, keep one flat list of file entries
        # Flatten current
        all_files: dict[str, dict] = {}
        for impl_group in current:
            for f in impl_group.get("files", []):
                all_files[f.get("component", f.get("path", ""))] = f

        # Merge new
        for f in new_specs:
            all_files[f.get("component", f.get("path", ""))] = f

        # Save as single implementation group
        self._save([{"files": list(all_files.values())}])
