"""
ImplementationDesignService – designs functions and workflows for components.

Takes component information from the ArchitectureDesignService and produces
detailed per-file implementation designs (classes, functions, dependencies,
patterns) that are compatible with the ProjectInitializer format.

Every class, method, and function receives a deterministic hash UID and
a ``related_to`` field linking back to architecture component UIDs.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json
from src.uid import make_uid


class ImplementationDesignService:
    """
    Generates implementation-level designs for architecture components
    and persists them in the ``implementation`` context.

    Storage format (shared with ProjectInitializer):
        {"files": [
            {
                "file": "src/services/foo.py",
                "purpose": "...",
                "classes": [{
                    "uid": "cls-...", "name": "...",
                    "responsibility": "...",
                    "methods": [{
                        "uid": "mtd-...", "name": "...",
                        "purpose": "...",
                        "input": "...", "processing": "...", "output": "...",
                        "related_to": ["arch-..."]
                    }],
                    "related_to": ["arch-..."]
                }],
                "functions": [{
                    "uid": "fn-...", "name": "...",
                    "purpose": "...",
                    "input": "...", "processing": "...", "output": "...",
                    "related_to": ["arch-..."]
                }],
                "dependencies": ["..."],
                "patterns": "..."
            }
        ]}
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
        return data.get("files", [])

    def _save(self, files: list[dict[str, Any]]) -> None:
        payload = {"files": files}
        if self._ctx.context_exists(self.CONTEXT_ID):
            self._ctx.update_context(self.CONTEXT_ID, payload, merge=False)
        else:
            self._ctx.create_context(self.CONTEXT_ID, payload)

    def design_functions_for_component(
        self,
        component: dict[str, Any],
        architecture: dict[str, Any],
        requirements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Design detailed implementation for a single component.

        Uses ``related_to`` to filter requirements to only those linked
        to this component, reducing prompt noise.

        Returns a dict containing the component name and its file specs.
        """
        arch_uid = component.get("uid", "")

        # Filter requirements to those related to this component
        filtered_reqs = self._filter_related_requirements(
            component, requirements or [],
        )
        reqs_block = json.dumps(filtered_reqs, indent=2) if filtered_reqs else "N/A"

        prompt = f"""You are an expert in software engineering.

Design detailed implementation for the following component based on the
architecture and requirements provided.  For each file the component needs,
specify its purpose, classes with methods, standalone functions, dependencies,
and design patterns.

For every method and function, describe input/processing/output (not just
parameters).

Return JSON only in this format:
{{
    "files": [
        {{
            "file": "src/services/component_name.py",
            "purpose": "What this file does and why it exists.",
            "classes": [
                {{
                    "name": "ClassName",
                    "responsibility": "What it does.",
                    "methods": [
                        {{
                            "name": "method_name",
                            "purpose": "What it does.",
                            "input": "What it receives.",
                            "processing": "How it works.",
                            "output": "What it returns."
                        }}
                    ]
                }}
            ],
            "functions": [
                {{
                    "name": "func_name",
                    "purpose": "What it does.",
                    "input": "What it receives.",
                    "processing": "How it works.",
                    "output": "What it returns."
                }}
            ],
            "dependencies": ["list", "of", "imports"],
            "patterns": "Notable design patterns or conventions used."
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

        # Assign UIDs and link back to architecture component
        for spec in file_specs:
            self._assign_uids(spec, arch_uid)

        self._merge_file_specs(file_specs)

        return {"component": component.get("component"), "files": file_specs}

    def provide_implementation_design(self) -> list[dict[str, Any]]:
        """Return the full implementation design for user review."""
        return self._load()

    @staticmethod
    def _assign_uids(file_entry: dict[str, Any], arch_uid: str) -> None:
        """Assign hash UIDs, set related_to, and default status for all items."""
        path = file_entry.get("file", "")
        for cls in file_entry.get("classes", []):
            cls_name = cls.get("name", "")
            cls["uid"] = make_uid("cls", path, cls_name)
            cls["related_to"] = [arch_uid] if arch_uid else []
            cls.setdefault("status", "new")
            for mtd in cls.get("methods", []):
                mtd["uid"] = make_uid("mtd", path, cls_name, mtd.get("name", ""))
                mtd["related_to"] = [arch_uid] if arch_uid else []
                mtd.setdefault("status", "new")
        for fn in file_entry.get("functions", []):
            fn["uid"] = make_uid("fn", path, fn.get("name", ""))
            fn["related_to"] = [arch_uid] if arch_uid else []
            fn.setdefault("status", "new")

    def _merge_file_specs(self, new_specs: list[dict[str, Any]]) -> None:
        """Merge new file specs into stored implementations by file path."""
        current = self._load()
        by_file: dict[str, dict[str, Any]] = {f["file"]: f for f in current}
        for spec in new_specs:
            by_file[spec["file"]] = spec
        self._save(list(by_file.values()))

    @staticmethod
    def _filter_related_requirements(
        component: dict[str, Any],
        requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Return only requirements whose ``related_to`` includes this
        component's UID, or that the component's ``related_to`` refers to.

        Falls back to all requirements if no links exist.
        """
        arch_uid = component.get("uid", "")
        comp_related = set(component.get("related_to", []))

        filtered = []
        for req in requirements:
            req_uid = req.get("uid", "")
            req_related = set(req.get("related_to", []))
            # Requirement points to this component, or component points to this requirement
            if arch_uid in req_related or req_uid in comp_related:
                filtered.append(req)

        # Fall back to all if no links found (avoids empty prompt)
        return filtered if filtered else requirements
