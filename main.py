import subprocess
import sys
import json
import os

from src.ai.model import ask_ai, ask_ai_json, ask_copilot
from src.context.context_manager import ContextManager
from src.ai.agent import AIAgent
from src.ai.ai_analysis_engine import AIAnalysisEngine
from src.services.requirement_management_service import RequirementManagementService
from src.services.architecture_design_service import ArchitectureDesignService
from src.services.implementation_design_service import ImplementationDesignService
from src.services.project_initializer import ProjectInitializer


# Shared instances – all services share one ContextManager so they
# read/write the same ``context/`` directory.
ctx = ContextManager()
agent = AIAgent(context_manager=ctx)
analysis_engine = AIAnalysisEngine(context_manager=ctx)
req_service = RequirementManagementService(context_manager=ctx)
arch_service = ArchitectureDesignService(context_manager=ctx)
impl_service = ImplementationDesignService(context_manager=ctx)
initializer = ProjectInitializer(context_manager=ctx)


def understand_project():
    tree_result = subprocess.run(
        ["tree", "-J", "-I", "node_modules|.git|dist|build"],
        capture_output=True,
        text=True,
        check=True
    )

    prompt = f"""
        You are expert of software engineering.
        
        Which file you want to read for understanding this project?
        
        Return should be in this format:
        {{
            "files": [
                {{
                    "path": "src/main.py",
                    "reason": "This file contains the main entry point of the application and orchestrates the overall workflow."
                }},
                {{
                    "path": "src/utils.py",
                    "reason": "This file contains utility functions that are used across the project."
                }}
            ],
            "description": "This project is a web application built with React and Node.js. It allows users to create and manage tasks. The main components include the frontend (React) and the backend (Node.js with Express). The project also uses MongoDB for data storage."
        }}

        Do not response plain text. Only return JSON format. Do not include any explanation or additional text.
        
        <workspace tree>
        {tree_result.stdout}
        </workspace tree>
    """

    result = ask_copilot(prompt)
    print("\n" + "="*80)
    print(result)
    print("="*80)

    result_json = json.loads(result)
    files = result_json.get("files", [])
    summaries = {}

    for file in files:
        file_path = file['path']
        file_contents = subprocess.run(
            ["cat", file_path],
            capture_output=True,
            text=True,
            check=True
        )

        prompt = f"""
            You are expert of software engineering.
            Please read the file {file_path} and summarize the content of this file in 3 sentences. Focus on the main purpose and functionality of this file.
            Return should be in this format:
            {{
                "summary": "This file contains the main entry point of the application and orchestrates the overall workflow."
            }}
            
            Do not response plain text. Only return JSON format. Do not include any explanation or additional text.

            <file content>
            {file_contents.stdout}
            </file content>
            """

        result = ask_copilot(prompt)
        result_json = json.loads(result)
        summaries[file_path] = result_json.get("summary", "")
    
    print("\n=== File Summaries ===")
    print(json.dumps(summaries, indent=4))
    key_file_summaries = "\n".join([f"{path}: {summary}" for path, summary in summaries.items()])

    prompt = f"""
        You are expert of software engineering.
        Please summarize the overall project based on the following file summaries. Focus on the main purpose and functionality of the project.
        Return should be in this format:
        {{
            "summary": "This project is a web application built with React and Node.js. It allows users to create and manage tasks. The main components include the frontend (React) and the backend (Node.js with Express). The project also uses MongoDB for data storage."
        }}
            
        <key file summaries>
        {key_file_summaries}
        </key file summaries>
        """
    
    result = ask_copilot(prompt)
    result_json = json.loads(result)
    print("\n=== Project Summary ===")
    print(result_json.get("summary", ""))

    # Persist via ContextManager
    overview_data = {
        "project_summary": result_json.get("summary", ""),
        "key_files": summaries
    }
    if ctx.context_exists("overview"):
        ctx.update_context("overview", overview_data, merge=False)
    else:
        ctx.create_context("overview", overview_data)


def intent_user_input(user_input: str) -> str:

    prompt = f"""
        You are an expert in software engineering.
        
        Please categorize the user's intent into one of the following categories:
        1. understand_project: The user wants to understand the overall project structure and key files.
        2. initialize_project: The user wants to initialize or construct full context for an existing project for AI agent coding assistance.
        3. new_feature: The user wants to add a new feature to the project.
        4. bug_fix: The user wants to fix a bug in the project.
        5. code_refactor: The user wants to refactor existing code for better readability or performance.
        6. ideation: The user wants to ideate on the project.
        7. dump_context: The user wants to export or dump all context data to JSON files.
        8. review: The user wants to review AI-generated items and approve or advance their status.
        9. other: The user's intent does not fit into any of the above categories.

        Return should be in this format:
        {{
            "intent": "understand_project"
        }}

        <user input>
        {user_input}
        </user input>
        """
    result = ask_ai_json(prompt)
    intent = result.get("intent", "other")
    print(f"Identified user intent: {intent}")
    
    return intent


def ideation():
    if not ctx.context_exists("overview"):
        print("No project overview found. Please run 'understand_project' intent first.")
        return
    
    overview = ctx.read_context("overview")
    project_summary = overview.get("project_summary", "")

    prompt = f"""
        You are expert of software engineering.
        Please generate 5 innovative ideas for improving the project based on the following project summary. 
        These ideas should be practical, feasible, and aligned with the project's goals.
        Return should be in this format:
        {{
            "ideas": [
                "Idea 1: Implement a dark mode for better user experience during nighttime.",
                "Idea 2: Add a mobile app version of the project to reach more users.",
                "Idea 3: Integrate AI-powered features to enhance functionality.",
                "Idea 4: Optimize the database queries for faster performance.",
                "Idea 5: Implement a plugin system to allow third-party extensions."
            ]
        }}

        <project summary>
        {project_summary}
        </project summary>
        """

    result = ask_copilot(prompt)
    result_json = json.loads(result)
    ideas = result_json.get("ideas", [])
    print("\n=== Innovative Ideas for Project Improvement ===")
    for idx, idea in enumerate(ideas, 1):
        print(f"{idx}. {idea}")
        
    # Persist via ContextManager
    ideas_data = {"ideas": ideas}
    if ctx.context_exists("ideas"):
        ctx.update_context("ideas", ideas_data, merge=False)
    else:
        ctx.create_context("ideas", ideas_data)


def analysis_requirements(user_input: str):
    if not ctx.context_exists("overview"):
        understand_project()
        
    overview = ctx.read_context("overview")
    current_requirements = req_service.get_all()

    # Use AIAnalysisEngine to analyse the feature and propose changes
    changes = analysis_engine.analyze_feature_description(
        feature_description=user_input,
        current_requirements=current_requirements,
    )

    # Apply changes through RequirementManagementService
    req_service.apply_changes(changes)

    # Retrieve the updated requirements
    updated = req_service.get_all()

    print("\n=== Requirements Updated ===")
    return updated


def design_software_architecture(requirements):
    # Get current architecture (or empty)
    current_arch = arch_service.get_architecture()

    # Wrap requirements as "create" changes for architectural analysis
    req_changes = [{"action": "create", "requirement": r} for r in requirements]

    # Detect architectural impact via AIAnalysisEngine
    arch_changes = analysis_engine.detect_architectural_impact(
        requirement_changes=req_changes,
        current_architecture=current_arch,
    )

    # Apply changes through ArchitectureDesignService
    result = arch_service.update_architecture(arch_changes)
    architecture = result["architecture"]

    print("\n=== Architecture Updated ===")
    return architecture


def design_implementation(architecture):
    """Design implementation-level functions for each component."""
    if not ctx.context_exists("architecture"):
        print("No architecture design found. Please run 'design_software_architecture' first.")
        return

    arch = arch_service.get_architecture()
    requirements = req_service.get_all()
    components = arch.get("components", [])

    # Notify which components need implementation design
    component_names = [c["component"] for c in components]
    affected = arch_service.notify_component_changes(component_names)

    print(f"\n=== Designing implementation for {len(affected)} component(s) ===")

    for comp in affected:
        print(f"  Designing: {comp['component']}...")
        impl_service.design_functions_for_component(
            component=comp,
            architecture=arch,
            requirements=requirements,
        )

    # Show the full implementation design
    design = impl_service.provide_implementation_design()
    print("\n=== Implementation Design ===")
    print(json.dumps(design, indent=4))


def handle_new_feature(user_input):
    new_requirements = analysis_requirements(user_input)
    architecture = design_software_architecture(new_requirements)
    design_implementation(architecture)


def initialize_project():
    """Construct full context for an existing project (overview → requirements → architecture → implementation)."""
    result = initializer.initialize()
    print(f"\nProject initialized with contexts: {', '.join(result['contexts'])}")
    print("The AI agent can now use this context for coding assistance.")


def dump_context():
    """Export all stored context from SQLite to individual JSON files."""
    written = ctx.dump_to_json()
    if not written:
        print("No contexts to dump.")
        return
    print(f"\n=== Dumped {len(written)} context(s) to JSON ===")
    for path in written:
        print(f"  ✓ {path}")


def _uid_label(item: dict) -> str:
    """Return a human-readable label for a UID-bearing item."""
    uid = item.get("uid", "?")
    name = (
        item.get("title")        # requirements
        or item.get("component")  # architecture
        or item.get("name")       # cls / mtd / fn
        or "unknown"
    )
    return f"[{uid}] {name}"


def review_items():
    """Interactive review of items with status ``new`` or ``reviewed``.

    Shows each item and lets the user advance its status:
        new → reviewed → done
    Or skip to leave it unchanged.
    """
    # Collect reviewable items (new first, then reviewed)
    new_items = ctx.find_by_status("new")
    reviewed_items = ctx.find_by_status("reviewed")
    items = new_items + reviewed_items

    if not items:
        print("\nNo items to review. Everything is up to date.")
        return

    print(f"\n=== Review: {len(new_items)} new, {len(reviewed_items)} reviewed ===")
    print("For each item:  [y] advance status  |  [n] skip  |  [q] quit\n")

    for item in items:
        current_status = item.get("status", "new")
        next_status = "reviewed" if current_status == "new" else "done"

        print("-" * 60)
        print(f"  {_uid_label(item)}")
        print(f"  Status: {current_status} → {next_status}")

        # Show relevant detail depending on item type
        for key in ("description", "responsibility", "purpose"):
            val = item.get(key)
            if val:
                print(f"  {key.capitalize()}: {val}")
                break

        answer = input(f"  Advance to '{next_status}'? [y/n/q] >> ").strip().lower()

        if answer == "q":
            print("  Review stopped.")
            break
        if answer in ("", "y", "yes"):
            uid = item.get("uid", "")
            if ctx.update_item_status(uid, next_status):
                print(f"  ✓ {uid} → {next_status}")
            else:
                print(f"  ✗ Could not update {uid}")
        else:
            print("  — skipped")

    print()


def main():
    print("Welcome to pofe - Source Code Understanding Tool!")
    print("What do you want?.")
    user_input = input(">> ")

    intent = intent_user_input(user_input)
    intent = intent.lower()

    if intent == "understand_project":
        understand_project()
    elif intent == "initialize_project":
        initialize_project()
    elif intent == "new_feature":
        handle_new_feature(user_input)
    elif intent == "bug_fix":
        print("You want to fix a bug. This functionality is not implemented yet.")
    elif intent == "code_refactor":
        print("You want to refactor code. This functionality is not implemented yet.")
    elif intent == "ideation":
        ideation()
    elif intent == "dump_context":
        dump_context()
    elif intent == "review":
        review_items()
    elif intent == "query":
        # Direct AI agent query using all available context
        response = agent.answer_query(user_input)
        print("\n=== AI Agent Response ===")
        print(response)
    elif intent == "summary":
        # Generate project summary
        summary = agent.summarize_project()
        print("\n=== Project Summary ===")
        print(summary)
    else:
        # Fall back to AI agent for anything else
        response = agent.answer_query(user_input)
        print("\n=== AI Agent Response ===")
        print(response)


if __name__ == "__main__":
    main()
