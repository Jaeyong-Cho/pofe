"""
AIAnalysisEngine – AI-driven requirement and architecture analysis.

Analyses new feature descriptions against the current project state and
proposes concrete changes to requirements and architecture.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json
from src.uid import make_uid


class AIAnalysisEngine:
    """
    Uses AI models to analyse feature descriptions and detect
    architectural impact.

    After AI returns changes, deterministic hash UIDs are assigned
    and ``related_to`` references are resolved from names to UIDs.
    """

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    # ------------------------------------------------------------------
    # Requirement analysis
    # ------------------------------------------------------------------

    def analyze_feature_description(
        self,
        feature_description: str,
        current_requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Analyse a feature description and return proposed requirement changes.

        Each entry has:
            action      – "create" | "update" | "delete"
            requirement – the requirement dict with uid, title, description,
                          tags, status, related_to

        Uses ``related_to`` traversal to include connected architecture
        components alongside each existing requirement for richer context.
        """
        # Enrich existing requirements with their related architecture components
        enriched_reqs = self._enrich_with_related(current_requirements)

        prompt = f"""You are an expert in software engineering.

Analyse the following new feature description against the current requirements.
Determine which requirements should be created, updated, or deleted.
Also categorize each requirement with appropriate tags.

Each requirement must include a "related_to" array listing the names of
architecture components that realise or support this requirement.
For updates, preserve existing related_to where applicable.

Return JSON only in this format:
{{
    "changes": [
        {{
            "action": "create",
            "requirement": {{
                "title": "...",
                "description": "...",
                "tags": ["..."],
                "status": "new",
                "related_to": ["ComponentName"]
            }}
        }},
        {{
            "action": "update",
            "requirement": {{
                "title": "...",
                "description": "...",
                "tags": ["..."],
                "status": "in progress",
                "related_to": ["ComponentName"]
            }}
        }},
        {{
            "action": "delete",
            "requirement": {{
                "title": "..."
            }}
        }}
    ]
}}

Do not include any explanation or additional text.

<feature description>
{feature_description}
</feature description>

<current requirements with related context>
{json.dumps(enriched_reqs, indent=2)}
</current requirements with related context>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        changes = result.get("changes", [])

        # Assign UIDs & resolve related_to on new/updated requirements
        self._resolve_requirement_changes(changes)
        return changes

    # ------------------------------------------------------------------
    # Architecture impact
    # ------------------------------------------------------------------

    def detect_architectural_impact(
        self,
        requirement_changes: list[dict[str, Any]],
        current_architecture: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Detect architectural impact of requirement changes.

        Uses ``related_to`` traversal to include connected implementation
        items for each architecture component, giving the AI a clearer
        picture of what already exists.

        Returns a list of architectural change suggestions, each with:
            action    – "create" | "update" | "delete"
            component – the component dict with uid, related_to
        """
        # Enrich architecture components with related implementation items
        enriched_arch = self._enrich_architecture_with_related(current_architecture)

        prompt = f"""You are an expert in software engineering.

Analyse the following requirement changes and determine their impact on the
current architecture.  Suggest which components should be created, updated, or
deleted.

Each component must include a "related_to" array listing the names of
implementation classes and functions that belong to it, plus the titles of
requirements it realises.  For updates, preserve existing related_to.

Return JSON only in this format:
{{
    "changes": [
        {{
            "action": "create",
            "component": {{
                "component": "ComponentName",
                "responsibilities": "...",
                "interactions": [
                    {{"OtherComponent": "..."}}
                ],
                "related_to": ["ClassName", "Requirement Title"]
            }}
        }},
        {{
            "action": "update",
            "component": {{
                "component": "ExistingComponent",
                "responsibilities": "...",
                "interactions": [
                    {{"OtherComponent": "..."}}
                ],
                "related_to": ["ClassName", "Requirement Title"]
            }}
        }}
    ]
}}

Do not include any explanation or additional text.

<requirement changes>
{json.dumps(requirement_changes, indent=2)}
</requirement changes>

<current architecture with related context>
{json.dumps(enriched_arch, indent=2)}
</current architecture with related context>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        changes = result.get("changes", [])

        # Assign UIDs & resolve related_to on new/updated components
        self._resolve_architecture_changes(changes, current_architecture)
        return changes

    # ------------------------------------------------------------------
    # UID assignment and related_to resolution
    # ------------------------------------------------------------------

    def _enrich_with_related(
        self, requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Enrich each requirement with its related architecture components.

        Returns a new list where each requirement has an additional
        ``_related_components`` field with the resolved items.
        """
        enriched = []
        for req in requirements:
            entry = dict(req)
            uid = req.get("uid", "")
            if uid:
                bundle = self._ctx.gather_related(uid, depth=1)
                related_comps = [
                    {"component": item.get("component", ""), "responsibilities": item.get("responsibilities", "")}
                    for ref_uid, item in bundle.get("related", {}).items()
                    if ref_uid.startswith("arch-")
                ]
                if related_comps:
                    entry["_related_components"] = related_comps
            enriched.append(entry)
        return enriched

    def _enrich_architecture_with_related(
        self, architecture: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Enrich each architecture component with its related implementation
        items and requirements.

        Returns a new architecture dict where each component has additional
        ``_related_impl`` and ``_related_reqs`` fields.
        """
        enriched_components = []
        for comp in architecture.get("components", []):
            entry = dict(comp)
            uid = comp.get("uid", "")
            if uid:
                bundle = self._ctx.gather_related(uid, depth=1)
                related_impl = []
                related_reqs = []
                for ref_uid, item in bundle.get("related", {}).items():
                    if ref_uid.startswith("req-"):
                        related_reqs.append({"title": item.get("title", ""), "description": item.get("description", "")})
                    elif ref_uid.startswith(("cls-", "mtd-", "fn-")):
                        related_impl.append({"name": item.get("name", ""), "purpose": item.get("purpose", "")})
                if related_impl:
                    entry["_related_impl"] = related_impl
                if related_reqs:
                    entry["_related_reqs"] = related_reqs
            enriched_components.append(entry)
        return {
            "components": enriched_components,
            "behaviors": architecture.get("behaviors", []),
        }

    def _resolve_requirement_changes(
        self, changes: list[dict[str, Any]],
    ) -> None:
        """Assign UIDs to new requirements; resolve related_to names → arch UIDs."""
        arch_lookup = self._build_arch_lookup()

        for change in changes:
            req = change.get("requirement", {})
            if change.get("action") in ("create", "update"):
                req.setdefault("related_to", [])
                # Assign uid based on title
                req["uid"] = make_uid("req", req.get("title", ""))
                # Resolve component names → arch UIDs
                req["related_to"] = [
                    arch_lookup.get(ref, ref) for ref in req["related_to"]
                ]

    def _resolve_architecture_changes(
        self,
        changes: list[dict[str, Any]],
        current_architecture: dict[str, Any],
    ) -> None:
        """Assign UIDs to new components; resolve related_to names → impl/req UIDs."""
        impl_lookup = self._build_impl_lookup()
        req_lookup = self._build_req_lookup()

        for change in changes:
            comp = change.get("component", {})
            if change.get("action") in ("create", "update"):
                comp_name = comp.get("component", "")
                comp["uid"] = make_uid("arch", comp_name)
                comp.setdefault("related_to", [])
                resolved = []
                for ref in comp["related_to"]:
                    if ref in impl_lookup:
                        resolved.append(impl_lookup[ref])
                    elif ref in req_lookup:
                        resolved.append(req_lookup[ref])
                    else:
                        resolved.append(ref)
                comp["related_to"] = resolved

    def _build_arch_lookup(self) -> dict[str, str]:
        """component name → uid from stored architecture context."""
        if not self._ctx.context_exists("architecture"):
            return {}
        data = self._ctx.read_context("architecture")
        arch = data.get("architecture", {})
        return {
            c.get("component", ""): c.get("uid", "")
            for c in arch.get("components", [])
        }

    def _build_impl_lookup(self) -> dict[str, str]:
        """class/function name → uid from stored implementation context."""
        if not self._ctx.context_exists("implementation"):
            return {}
        data = self._ctx.read_context("implementation")
        lookup: dict[str, str] = {}
        for f in data.get("files", []):
            for cls in f.get("classes", []):
                lookup[cls.get("name", "")] = cls.get("uid", "")
                for mtd in cls.get("methods", []):
                    mtd_name = mtd.get("name", "")
                    mtd_uid = mtd.get("uid", "")
                    lookup[f"{cls.get('name', '')}.{mtd_name}"] = mtd_uid
                    lookup.setdefault(mtd_name, mtd_uid)
            for fn in f.get("functions", []):
                lookup[fn.get("name", "")] = fn.get("uid", "")
        return lookup

    def _build_req_lookup(self) -> dict[str, str]:
        """requirement title → uid from stored requirements context."""
        if not self._ctx.context_exists("requirements"):
            return {}
        data = self._ctx.read_context("requirements")
        return {
            r.get("title", ""): r.get("uid", "")
            for r in data.get("requirements", [])
        }
