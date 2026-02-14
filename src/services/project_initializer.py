"""
ProjectInitializer – constructs full context for an existing project.

Uses a bottom-up analysis pipeline: reads source code first to build
concrete understanding, then progressively derives higher-level context.

This is the entry point for bootstrapping context on an existing project.
"""

import subprocess
import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json
from src.uid import make_uid
from src.services.requirement_management_service import RequirementManagementService
from src.services.architecture_design_service import ArchitectureDesignService
from src.services.implementation_design_service import ImplementationDesignService


class ProjectInitializer:
    """
    Orchestrates full context construction for an existing project.

    Pipeline (bottom-up):
        1. Scan & read source files, analyse each file's implementation
        2. Infer architecture from implementation analysis
        3. Infer requirements from architecture
        4. Build overview from all accumulated context

    Every step feeds into the next, building understanding from concrete
    code upward to abstract project-level context.
    """

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend
        self._req = RequirementManagementService(context_manager=self._ctx, backend=backend)
        self._arch = ArchitectureDesignService(context_manager=self._ctx, backend=backend)
        self._impl = ImplementationDesignService(context_manager=self._ctx, backend=backend)

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def initialize(self, tree_ignore: str = "node_modules|.git|dist|build|.venv|__pycache__") -> dict[str, Any]:
        """
        Run the bottom-up initialisation pipeline.

        Returns a summary dict with status for each context layer.
        """
        print("\n=== Step 1/4: Scanning source & analysing implementation ===")
        source_files, implementation = self._build_implementation(tree_ignore)

        print("\n=== Step 2/4: Inferring architecture ===")
        architecture = self._build_architecture(source_files, implementation)

        print("\n=== Step 3/4: Inferring requirements ===")
        requirements = self._build_requirements(architecture, implementation)

        print("\n=== Step 4/4: Building overview ===")
        self._build_overview(implementation, architecture, requirements)

        print("\n=== Initialization complete ===")
        contexts = self._ctx.list_contexts()
        print(f"Contexts available: {', '.join(contexts)}")

        return {
            "status": "initialized",
            "contexts": contexts,
        }

    # ------------------------------------------------------------------
    # Step 1 – implementation (analyse each source file)
    # ------------------------------------------------------------------

    def _build_implementation(
        self, tree_ignore: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """Scan tree, read all source files, analyse each file's implementation.

        Returns:
            (source_files, implementation) – raw source mapping and
            per-file implementation analysis list.
        """
        tree_output = self._get_project_tree(tree_ignore)
        all_paths = self._extract_file_paths(tree_output)
        print(f"  Found {len(all_paths)} source file(s)")

        # Read every source file
        source_files: dict[str, str] = {}
        for path in all_paths:
            content = self._read_file(path)
            if content is not None:
                source_files[path] = content

        # Analyse implementation of each file
        implementation: list[dict[str, Any]] = []
        for path, content in source_files.items():
            print(f"  Analysing: {path}")
            result = ask_ai_json(
                self._prompt_analyse_implementation(path, content),
                backend=self._backend,
            )
            result["file"] = path
            self._assign_impl_uids(result)
            implementation.append(result)

        self._save_context("implementation", {"files": implementation})
        print(f"  ✓ Implementation analysis saved ({len(implementation)} file(s))")
        return source_files, implementation

    # ------------------------------------------------------------------
    # Step 2 – architecture (from implementation)
    # ------------------------------------------------------------------

    def _build_architecture(
        self,
        source_files: dict[str, str],
        implementation: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Derive architecture from per-file implementation analysis."""
        result = ask_ai_json(
            self._prompt_infer_architecture(source_files, implementation),
            backend=self._backend,
        )

        architecture = {
            "components": result.get("components", []),
            "behaviors": result.get("behaviors", []),
        }
        self._assign_arch_uids(architecture, implementation)

        # Back-populate related_to on implementation items
        self._backfill_impl_related_to(implementation, architecture)
        self._save_context("implementation", {"files": implementation})

        self._save_context("architecture", {"architecture": architecture})
        print(f"  ✓ {len(architecture['components'])} component(s), "
              f"{len(architecture['behaviors'])} behavior(s) saved")
        return architecture

    # ------------------------------------------------------------------
    # Step 3 – requirements (from architecture)
    # ------------------------------------------------------------------

    def _build_requirements(
        self,
        architecture: dict[str, Any],
        implementation: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Infer requirements from architecture and implementation analysis."""
        result = ask_ai_json(
            self._prompt_infer_requirements(architecture, implementation),
            backend=self._backend,
        )
        requirements = result.get("requirements", [])
        self._assign_req_uids(requirements, architecture)

        # Back-populate related_to on architecture components
        self._backfill_arch_related_to(architecture, requirements)
        self._save_context("architecture", {"architecture": architecture})

        self._save_context("requirements", {"requirements": requirements})
        print(f"  ✓ {len(requirements)} requirement(s) saved")
        return requirements

    # ------------------------------------------------------------------
    # Step 4 – overview (from all context)
    # ------------------------------------------------------------------

    def _build_overview(
        self,
        implementation: list[dict[str, Any]],
        architecture: dict[str, Any],
        requirements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build project overview from all accumulated context."""
        result = ask_ai_json(
            self._prompt_build_overview(implementation, architecture, requirements),
            backend=self._backend,
        )

        overview_data = {
            "project_summary": result.get("project_summary", ""),
            "tech_stack": result.get("tech_stack", []),
            "key_files": {f["file"]: f.get("purpose", "") for f in implementation},
        }
        self._save_context("overview", overview_data)
        print(f"  ✓ Overview context saved")
        return overview_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_impl_uids(file_entry: dict[str, Any]) -> None:
        """Assign hash-based UIDs to all classes, methods, and functions in a file."""
        path = file_entry.get("file", "")
        for cls in file_entry.get("classes", []):
            cls_name = cls.get("name", "")
            cls["uid"] = make_uid("cls", path, cls_name)
            for mtd in cls.get("methods", []):
                mtd["uid"] = make_uid("mtd", path, cls_name, mtd.get("name", ""))
        for fn in file_entry.get("functions", []):
            fn["uid"] = make_uid("fn", path, fn.get("name", ""))

    @staticmethod
    def _assign_arch_uids(
        architecture: dict[str, Any],
        implementation: list[dict[str, Any]],
    ) -> None:
        """Assign hash UIDs to architecture components and resolve related_to."""
        impl_lookup: dict[str, str] = {}
        for f in implementation:
            for cls in f.get("classes", []):
                impl_lookup[cls.get("name", "")] = cls.get("uid", "")
                for mtd in cls.get("methods", []):
                    mtd_name = mtd.get("name", "")
                    mtd_uid = mtd.get("uid", "")
                    impl_lookup[f"{cls.get('name', '')}.{mtd_name}"] = mtd_uid
                    impl_lookup.setdefault(mtd_name, mtd_uid)
            for fn in f.get("functions", []):
                impl_lookup[fn.get("name", "")] = fn.get("uid", "")

        for comp in architecture.get("components", []):
            comp_name = comp.get("component", "")
            comp["uid"] = make_uid("arch", comp_name)
            resolved = []
            for ref in comp.get("related_to", []):
                if ref in impl_lookup:
                    resolved.append(impl_lookup[ref])
                else:
                    resolved.append(ref)
            comp["related_to"] = resolved

    @staticmethod
    def _assign_req_uids(
        requirements: list[dict[str, Any]],
        architecture: dict[str, Any],
    ) -> None:
        """Assign hash UIDs to requirements and resolve related_to."""
        arch_lookup: dict[str, str] = {}
        for comp in architecture.get("components", []):
            arch_lookup[comp.get("component", "")] = comp.get("uid", "")

        for req in requirements:
            req["uid"] = make_uid("req", req.get("title", ""))
            resolved = []
            for ref in req.get("related_to", []):
                if ref in arch_lookup:
                    resolved.append(arch_lookup[ref])
                else:
                    resolved.append(ref)
            req["related_to"] = resolved

    def _save_context(self, context_id: str, data: dict[str, Any]) -> None:
        """Create or overwrite a context."""
        if self._ctx.context_exists(context_id):
            self._ctx.update_context(context_id, data, merge=False)
        else:
            self._ctx.create_context(context_id, data)

    def _get_project_tree(self, ignore_pattern: str) -> str:
        result = subprocess.run(
            ["tree", "-J", "-I", ignore_pattern],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def _read_file(self, path: str) -> str | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            print(f"  ⚠ Skipping (binary or unreadable): {path}")
            return None

    def _extract_file_paths(self, tree_json: str) -> list[str]:
        """Extract all file paths from `tree -J` output."""
        try:
            tree_data = json.loads(tree_json)
        except json.JSONDecodeError:
            return []

        paths: list[str] = []

        def _walk(entries: list[dict], prefix: str = "") -> None:
            for entry in entries:
                name = entry.get("name", "")
                full = f"{prefix}/{name}" if prefix else name
                if entry.get("type") == "file":
                    paths.append(full)
                elif entry.get("type") == "directory":
                    _walk(entry.get("contents", []), full)

        _walk(tree_data)
        return paths

    def _format_source_files(self, source_files: dict[str, str]) -> str:
        """Format source files into a single text block for prompt inclusion."""
        parts: list[str] = []
        for path, content in source_files.items():
            parts.append(f"--- {path} ---\n{content}")
        return "\n\n".join(parts)

    def _backfill_impl_related_to(
        self,
        implementation: list[dict[str, Any]],
        architecture: dict[str, Any],
    ) -> None:
        """Set related_to on implementation classes/functions/methods from architecture."""
        # Build reverse map: impl_uid → list of arch uids
        reverse: dict[str, list[str]] = {}
        for comp in architecture.get("components", []):
            arch_uid = comp.get("uid", "")
            for impl_uid in comp.get("related_to", []):
                reverse.setdefault(impl_uid, []).append(arch_uid)

        for file_entry in implementation:
            for cls in file_entry.get("classes", []):
                cls["related_to"] = reverse.get(cls.get("uid", ""), [])
                for mtd in cls.get("methods", []):
                    mtd["related_to"] = reverse.get(mtd.get("uid", ""), [])
            for fn in file_entry.get("functions", []):
                fn["related_to"] = reverse.get(fn.get("uid", ""), [])

    def _backfill_arch_related_to(
        self,
        architecture: dict[str, Any],
        requirements: list[dict[str, Any]],
    ) -> None:
        """Merge requirement uids into architecture components' related_to."""
        # Build reverse map: arch_uid → list of req uids
        reverse: dict[str, list[str]] = {}
        for req in requirements:
            req_uid = req.get("uid", "")
            for arch_uid in req.get("related_to", []):
                reverse.setdefault(arch_uid, []).append(req_uid)

        for comp in architecture.get("components", []):
            existing = comp.get("related_to", [])
            extra = reverse.get(comp.get("uid", ""), [])
            # Merge without duplicates, keep order
            seen = set(existing)
            for uid in extra:
                if uid not in seen:
                    existing.append(uid)
                    seen.add(uid)
            comp["related_to"] = existing

    # ------------------------------------------------------------------
    # Prompt templates
    # ------------------------------------------------------------------

    def _prompt_analyse_implementation(self, path: str, content: str) -> str:
        return f"""You are an expert in software engineering.

Analyse the implementation of the file below.  Identify:
- The file's purpose and role in the project
- All classes, their responsibilities, and key methods
- All standalone functions and their purposes
- Data structures and models used
- External dependencies and integrations
- Error handling patterns

For methods and functions, describe input/processing/output instead of parameters.

Return JSON only in this format:
{{
    "purpose": "What this file does and why it exists.",
    "classes": [
        {{
            "name": "ClassName",
            "responsibility": "What it does.",
            "methods": [
                {{
                    "name": "do_thing",
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
            "name": "helper",
            "purpose": "What it does.",
            "input": "What it receives.",
            "processing": "How it works.",
            "output": "What it returns."
        }}
    ],
    "dependencies": ["list", "of", "imports"],
    "patterns": "Notable design patterns or conventions used."
}}

Do not include any explanation or additional text.

<file: {path}>
{content}
</file>
"""

    def _prompt_infer_architecture(
        self,
        source_files: dict[str, str],
        implementation: list[dict[str, Any]],
    ) -> str:
        source_block = self._format_source_files(source_files)
        return f"""You are an expert in software engineering.

Based on the per-file implementation analysis AND the actual source code below,
infer the system architecture.  Identify real components, their boundaries,
and how they interact.  Derive this from the concrete code structure.

Each component must include a "related_to" array listing the names of
implementation classes and functions that belong to that component.
Use the exact class/function names from the implementation analysis.

Return JSON only in this format:
{{
    "components": [
        {{
            "component": "ComponentName",
            "responsibilities": "What it does.",
            "interactions": [
                {{"OtherComponent": "How they interact."}}
            ],
            "related_to": ["ClassName", "helper_func"]
        }}
    ],
    "behaviors": [
        {{
            "senario": "Scenario name",
            "steps": [
                "Actor -> Component: Action.",
                "Component -> Component: Action."
            ]
        }}
    ]
}}

Do not include any explanation or additional text.

<implementation analysis>
{json.dumps(implementation, indent=2)}
</implementation analysis>

<source code>
{source_block}
</source code>
"""

    def _prompt_infer_requirements(
        self,
        architecture: dict[str, Any],
        implementation: list[dict[str, Any]],
    ) -> str:
        return f"""You are an expert in software engineering.

Based on the architecture and implementation analysis below, infer the
functional and non-functional requirements that this project currently
fulfils or should fulfil.  Derive requirements from the concrete
components, functions, and behaviours already identified.

Each requirement must include a "related_to" array listing the names of
architecture components that realise or support this requirement.
Use the exact component names from the architecture analysis.

Return JSON only in this format:
{{
    "requirements": [
        {{
            "title": "Requirement title",
            "description": "Detailed description of the requirement.",
            "tags": ["tag1", "tag2"],
            "status": "done",
            "related_to": ["ComponentA"]
        }}
    ]
}}

Use status "done" for features that clearly exist, "in progress" for
partially implemented features, and "new" for inferred but unimplemented needs.

Do not include any explanation or additional text.

<architecture>
{json.dumps(architecture, indent=2)}
</architecture>

<implementation analysis>
{json.dumps(implementation, indent=2)}
</implementation analysis>
"""

    def _prompt_build_overview(
        self,
        implementation: list[dict[str, Any]],
        architecture: dict[str, Any],
        requirements: list[dict[str, Any]],
    ) -> str:
        return f"""You are an expert in software engineering.

Based on the implementation analysis, architecture, and requirements below,
produce a concise project overview.

Return JSON only in this format:
{{
    "project_summary": "2-3 sentence summary of what the project does, its purpose, and main value.",
    "tech_stack": ["Python", "FastAPI", "..."]
}}

Do not include any explanation or additional text.

<implementation analysis>
{json.dumps(implementation, indent=2)}
</implementation analysis>

<architecture>
{json.dumps(architecture, indent=2)}
</architecture>

<requirements>
{json.dumps(requirements, indent=2)}
</requirements>
"""
