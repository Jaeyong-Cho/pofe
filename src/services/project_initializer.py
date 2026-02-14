"""
ProjectInitializer – constructs full context for an existing project.

Scans a codebase and builds all context layers (overview, requirements,
architecture, implementation) so that the AI agent has the complete
picture needed for coding assistance.

This is the entry point for bootstrapping context on an existing project.
"""

import subprocess
import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json, ask_copilot
from src.services.requirement_management_service import RequirementManagementService
from src.services.architecture_design_service import ArchitectureDesignService
from src.services.implementation_design_service import ImplementationDesignService


class ProjectInitializer:
    """
    Orchestrates full context construction for an existing project.

    Pipeline:
        1. Scan project tree and read key files  → ``overview`` context
        2. Infer requirements from codebase       → ``requirements`` context
        3. Infer architecture from codebase        → ``architecture`` context
        4. Infer implementation design             → ``implementation`` context

    Every step is incremental: if a context already exists it is replaced
    with the freshly analysed version.
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
        Run the complete initialisation pipeline.

        Returns a summary dict with status for each context layer.
        """
        print("\n=== Step 1/4: Scanning project & building overview ===")
        overview, source_files = self._build_overview(tree_ignore)

        print("\n=== Step 2/4: Inferring requirements ===")
        requirements = self._build_requirements(overview, source_files)

        print("\n=== Step 3/4: Inferring architecture ===")
        architecture = self._build_architecture(overview, requirements, source_files)

        print("\n=== Step 4/4: Inferring implementation design ===")
        self._build_implementation(overview, requirements, architecture)

        print("\n=== Initialization complete ===")
        contexts = self._ctx.list_contexts()
        print(f"Contexts available: {', '.join(contexts)}")

        return {
            "status": "initialized",
            "contexts": contexts,
        }

    # ------------------------------------------------------------------
    # Step 1 – overview
    # ------------------------------------------------------------------

    def _build_overview(self, tree_ignore: str) -> tuple[dict[str, Any], dict[str, str]]:
        """Scan the project tree, read key files, and produce an overview.

        Returns:
            (overview_data, source_files) – the overview dict and a mapping
            of file-path → full source content for use by later steps.
        """
        tree_output = self._get_project_tree(tree_ignore)

        # Ask AI which files to read
        key_files_result = ask_ai_json(
            self._prompt_select_key_files(tree_output),
            backend=self._backend,
        )

        files = key_files_result.get("files", [])
        description = key_files_result.get("description", "")
        print(f"  Identified {len(files)} key file(s)")

        # Read each file and keep full source for later steps
        source_files: dict[str, str] = {}
        summaries: dict[str, str] = {}
        for f in files:
            path = f["path"]
            content = self._read_file(path)
            if content is None:
                continue
            source_files[path] = content
            summary_result = ask_ai_json(
                self._prompt_summarise_file(path, content),
                backend=self._backend,
            )
            summaries[path] = summary_result.get("summary", "")
            print(f"  Summarised: {path}")

        # Produce overall project summary
        key_file_text = "\n".join(f"{p}: {s}" for p, s in summaries.items())
        project_summary_result = ask_ai_json(
            self._prompt_project_summary(key_file_text),
            backend=self._backend,
        )
        project_summary = project_summary_result.get("summary", description)

        overview_data = {
            "project_summary": project_summary,
            "key_files": summaries,
        }
        self._save_context("overview", overview_data)
        print(f"  ✓ Overview context saved")
        return overview_data, source_files

    # ------------------------------------------------------------------
    # Step 2 – requirements
    # ------------------------------------------------------------------

    def _build_requirements(
        self,
        overview: dict[str, Any],
        source_files: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Infer requirements from the project overview and actual source code."""
        result = ask_ai_json(
            self._prompt_infer_requirements(overview, source_files),
            backend=self._backend,
        )
        requirements = result.get("requirements", [])

        self._save_context("requirements", {"requirements": requirements})
        print(f"  ✓ {len(requirements)} requirement(s) saved")
        return requirements

    # ------------------------------------------------------------------
    # Step 3 – architecture
    # ------------------------------------------------------------------

    def _build_architecture(
        self,
        overview: dict[str, Any],
        requirements: list[dict[str, Any]],
        source_files: dict[str, str],
    ) -> dict[str, Any]:
        """Infer architecture from overview, requirements, and actual source code."""
        result = ask_ai_json(
            self._prompt_infer_architecture(overview, requirements, source_files),
            backend=self._backend,
        )

        architecture = {
            "components": result.get("components", []),
            "behaviors": result.get("behaviors", []),
        }
        self._save_context("architecture", {"architecture": architecture})
        print(f"  ✓ {len(architecture['components'])} component(s), "
              f"{len(architecture['behaviors'])} behavior(s) saved")
        return architecture

    # ------------------------------------------------------------------
    # Step 4 – implementation design
    # ------------------------------------------------------------------

    def _build_implementation(
        self,
        overview: dict[str, Any],
        requirements: list[dict[str, Any]],
        architecture: dict[str, Any],
    ) -> None:
        """Generate implementation-level function designs for each component."""
        components = architecture.get("components", [])
        print(f"  Designing functions for {len(components)} component(s)...")

        for comp in components:
            name = comp.get("component", "unknown")
            print(f"    → {name}")
            self._impl.design_functions_for_component(
                component=comp,
                architecture=architecture,
                requirements=requirements,
            )

        design = self._impl.provide_implementation_design()
        print(f"  ✓ Implementation design saved")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
            result = subprocess.run(
                ["cat", path],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError:
            print(f"  ⚠ Could not read: {path}")
            return None

    def _format_source_files(self, source_files: dict[str, str]) -> str:
        """Format source files into a single text block for prompt inclusion."""
        parts: list[str] = []
        for path, content in source_files.items():
            parts.append(f"--- {path} ---\n{content}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Prompt templates
    # ------------------------------------------------------------------

    def _prompt_select_key_files(self, tree_json: str) -> str:
        return f"""You are an expert in software engineering.

Which files should be read to understand this project?
Select the most important files that reveal the project's purpose,
architecture, and key functionality.

Return JSON only in this format:
{{
    "files": [
        {{"path": "src/main.py", "reason": "Main entry point."}},
        {{"path": "src/utils.py", "reason": "Core utility functions."}}
    ],
    "description": "Brief one-line project description."
}}

Do not include any explanation or additional text.

<workspace tree>
{tree_json}
</workspace tree>
"""

    def _prompt_summarise_file(self, path: str, content: str) -> str:
        return f"""You are an expert in software engineering.

Summarize the file {path} in 3 sentences.
Focus on purpose, key classes/functions, and how it fits into the project.

Return JSON only:
{{"summary": "..."}}

Do not include any explanation or additional text.

<file content>
{content}
</file content>
"""

    def _prompt_project_summary(self, key_file_summaries: str) -> str:
        return f"""You are an expert in software engineering.

Summarize the overall project based on the key file summaries below.
Focus on the project's purpose, tech stack, and main functionality.

Return JSON only:
{{"summary": "..."}}

Do not include any explanation or additional text.

<key file summaries>
{key_file_summaries}
</key file summaries>
"""

    def _prompt_infer_requirements(
        self,
        overview: dict[str, Any],
        source_files: dict[str, str],
    ) -> str:
        source_block = self._format_source_files(source_files)
        return f"""You are an expert in software engineering.

Based on the project overview AND the actual source code below, infer the
functional and non-functional requirements that this project currently
fulfils or should fulfil.  Use the source code to identify concrete
capabilities, edge cases, and implicit requirements.

Return JSON only in this format:
{{
    "requirements": [
        {{
            "title": "Requirement title",
            "description": "Detailed description of the requirement.",
            "tags": ["tag1", "tag2"],
            "status": "done"
        }}
    ]
}}

Use status "done" for features that clearly exist, "in progress" for
partially implemented features, and "new" for inferred but unimplemented needs.

Do not include any explanation or additional text.

<project overview>
{json.dumps(overview, indent=2)}
</project overview>

<source code>
{source_block}
</source code>
"""

    def _prompt_infer_architecture(
        self,
        overview: dict[str, Any],
        requirements: list[dict[str, Any]],
        source_files: dict[str, str],
    ) -> str:
        source_block = self._format_source_files(source_files)
        return f"""You are an expert in software engineering.

Based on the project overview, requirements, AND the actual source code below,
infer the system architecture.  Use the source code to identify real components,
modules, classes, and their interactions rather than guessing from summaries.

Return JSON only in this format:
{{
    "components": [
        {{
            "component": "ComponentName",
            "responsibilities": "What it does.",
            "interactions": [
                {{"OtherComponent": "How they interact."}}
            ]
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

<project overview>
{json.dumps(overview, indent=2)}
</project overview>

<requirements>
{json.dumps(requirements, indent=2)}
</requirements>

<source code>
{source_block}
</source code>
"""
