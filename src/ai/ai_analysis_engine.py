"""
AIAnalysisEngine – AI-driven requirement and architecture analysis.

Analyses new feature descriptions against the current project state and
proposes concrete changes to requirements and architecture.
"""

import json
from typing import Any

from src.context.context_manager import ContextManager
from src.ai.model import ask_ai_json


class AIAnalysisEngine:
    """
    Uses AI models to analyse feature descriptions and detect
    architectural impact.
    """

    def __init__(
        self,
        context_manager: ContextManager | None = None,
        backend: str = "copilot",
    ):
        self._ctx = context_manager or ContextManager()
        self._backend = backend

    def analyze_feature_description(
        self,
        feature_description: str,
        current_requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Analyse a feature description and return proposed requirement changes.

        Each entry has:
            action   – "create" | "update" | "delete"
            requirement – the requirement dict (with title, description, tags,
                          status)
        """
        prompt = f"""You are an expert in software engineering.

Analyse the following new feature description against the current requirements.
Determine which requirements should be created, updated, or deleted.
Also categorize each requirement with appropriate tags.

Return JSON only in this format:
{{
    "changes": [
        {{
            "action": "create",
            "requirement": {{
                "title": "...",
                "description": "...",
                "tags": ["..."],
                "status": "new"
            }}
        }},
        {{
            "action": "update",
            "requirement": {{
                "title": "...",
                "description": "...",
                "tags": ["..."],
                "status": "in progress"
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

<current requirements>
{json.dumps(current_requirements, indent=2)}
</current requirements>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        return result.get("changes", [])

    def detect_architectural_impact(
        self,
        requirement_changes: list[dict[str, Any]],
        current_architecture: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Detect architectural impact of requirement changes.

        Returns a list of architectural change suggestions, each with:
            action    – "create" | "update" | "delete"
            component – the component dict
        """
        prompt = f"""You are an expert in software engineering.

Analyse the following requirement changes and determine their impact on the
current architecture.  Suggest which components should be created, updated, or
deleted.

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
                ]
            }}
        }},
        {{
            "action": "update",
            "component": {{
                "component": "ExistingComponent",
                "responsibilities": "...",
                "interactions": [
                    {{"OtherComponent": "..."}}
                ]
            }}
        }}
    ]
}}

Do not include any explanation or additional text.

<requirement changes>
{json.dumps(requirement_changes, indent=2)}
</requirement changes>

<current architecture>
{json.dumps(current_architecture, indent=2)}
</current architecture>
"""
        result = ask_ai_json(prompt, backend=self._backend)
        return result.get("changes", [])
