import subprocess
import sys
import json
import os


def ask_copilot(prompt: str, model: str = "gpt-4.1") -> str:
    cmd = [
        "copilot",
        "--stream", "on",
        "-s",
        "--allow-all-paths",
        "--model", model,
        "-p", prompt
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running copilot cli: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'copilot' command not found. Please ensure Copilot CLI is installed.", file=sys.stderr)
        sys.exit(1)


def ask_ollama(prompt: str, model: str = "qwen3:14b") -> str:
    try:
        import ollama
    except ImportError:
        print("Error: ollama package not installed. Install with: pip install ollama", file=sys.stderr)
        sys.exit(1)
    
    response = ollama.chat(
        model=model,
        messages=[{
            'role': 'user',
            'content': prompt
        }]
    )
    
    return response['message']['content'].strip()


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

    # write summary to context/summary.json
    if not os.path.exists("context"):
        os.makedirs("context")

    with open("context/overview.json", "w") as f:
        json.dump({
            "project_summary": result_json.get("summary", ""),
            "key_files": summaries
        }, f, indent=4)


def intent_user_input(user_input: str) -> str:

    prompt = f"""
        You are an expert in software engineering.
        
        Please categorize the user's intent into one of the following categories:
        1. understand_project: The user wants to understand the overall project structure and key files.
        2. new_feature: The user wants to add a new feature to the project.
        3. bug_fix: The user wants to fix a bug in the project.
        4. code_refactor: The user wants to refactor existing code for better readability or performance.
        5. ideation: The user wants to ideate on the project.
        6. other: The user's intent does not fit into any of the above categories.

        Return should be in this format:
        {{
            "intent": "understand_project"
        }}

        <user input>
        {user_input}
        </user input>
        """
    result = ask_copilot(prompt)
    result_json = json.loads(result)
    intent = result_json.get("intent", "other")
    print(f"Identified user intent: {intent}")
    
    return intent


def ideation():
    # read context/overview.json
    if not os.path.exists("context/overview.json"):
        print("No project overview found. Please run 'understand_project' intent first.")
        return
    
    with open("context/overview.json", "r") as f:
        overview = json.load(f)

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
        
    # write ideas to context/ideas.json
    if not os.path.exists("context"):
        os.makedirs("context")
        
    with open("context/ideas.json", "w") as f:
        json.dump({
            "ideas": ideas
        }, f, indent=4)


def analysis_requirements(user_input: str):
    if not os.path.exists("context/overview.json"):
        understand_project()
        
    with open("context/overview.json", "r") as f:
        overview = json.load(f)
    
    if not os.path.exists("context/requirements.json"):
        requirements = None
    else:
        with open("context/requirements.json", "r") as f:
            requirements = json.load(f)

    prompt = f"""
        You are an expert in software engineering.
        Please analyze the requirements for implementing a new feature based on the following project overview and existing requirements. 
        If there are no existing requirements, please generate new requirements based on the project overview.
        Return should be in this format:
        {{
            "requirements": [
                {{
                    "title": "User Authentication",
                    "description": "Implement a secure user authentication system that allows users to register, log in, and manage their accounts.",
                    "tags": ["authentication", "security", "user management"],
                    "status": "new" or "in progress" or "done"
                }},
                {{
                    "title": "Task Management",
                    "description": "Create a task management feature that allows users to create, edit, and delete tasks. Tasks should have due dates and priority levels.",
                    "tags": ["task management", "CRUD", "user interface"],
                    "status": "new" or "in progress" or "done"
                }}
            ]
        }}

        <project overview>
        {overview.get("project_summary", "")}
        </project overview>
        
        <existing requirements>
        {json.dumps(requirements, indent=4) if requirements else "No existing requirements."}
        </existing requirements>

        <user suggested feature>
        {user_input}
        </user suggested feature>
        """
    
    result = ask_copilot(prompt)
    new_requirements = json.loads(result).get("requirements", [])

    with open("context/requirements.json", "w") as f:
        json.dump(json.loads(result), f, indent=4)

    print("\n=== Analyzed Requirements for New Feature ===")
    print(result)

    return new_requirements


def design_software_architecture(requirements):
    prompt = f"""
        You are an expert in software engineering.
        Please design a software architecture for implementing the following requirements. 
        The architecture should include the main components, their responsibilities, and how they interact with each other. 
        Return should be in this format:
        {{
            "components": [
                {{
                    "component": "AuthenticationService",
                    "responsibilities": "Handles user registration, login, and account management. Ensures secure authentication and authorization.",
                    "interactions": [
                        {{
                            "TaskManagementService": "Receives user authentication status and permissions to control access to task management features."
                        }}
                    ]
                }},
                {{
                    "component": "TaskManagementService",
                    "responsibilities": "Manages task creation, editing, deletion, and retrieval. Handles task prioritization and due dates.",
                    "interactions": [
                        {{
                            "User Interface": "Receives user input for task management operations."
                        }},
                        {{
                            "Database": "Stores and retrieves task data."
                        }}
                    ]
                }}
            ],
            "behaviors": [
                {{
                    "senario": "User Registration",
                    "steps": [
                        "User -> User Interface: Submits registration form.",
                        "User Interface -> AuthenticationService: Sends registration data.",
                        "AuthenticationService -> Database: Stores user data.",
                        "AuthenticationService -> User Interface: Returns success response."
                    ]
                }},
                {{
                    "senario": "Task Creation",
                    "steps": [
                        "User -> User Interface: Submits new task form.",
                        "User Interface -> TaskManagementService: Sends task data.",
                        "TaskManagementService -> Database: Stores task data.",
                        "TaskManagementService -> User Interface: Returns success response."
                    ]
                }},
            ]
        }}

        <requirements>
        {json.dumps(requirements, indent=4)}
        </requirements>
        """
    
    result = ask_copilot(prompt)
    architecture = json.loads(result)
    print("\n=== Designed Software Architecture ===")
    print(result)

    with open("context/architecture.json", "w") as f:
        json.dump({
            "architecture": architecture
        }, f, indent=4)

    return architecture


def handle_new_feature(user_input):
    new_requirements = analysis_requirements(user_input)
    design_software_architecture(new_requirements)
    # implement
    # test
    # validate


def main():
    print("Welcome to pofe - Source Code Understanding Tool!")
    print("What do you want?.")
    user_input = input(">> ")

    intent = intent_user_input(user_input)
    intent = intent.lower()

    if intent == "understand_project":
        understand_project()
    elif intent == "new_feature":
        handle_new_feature(user_input)
    elif intent == "bug_fix":
        print("You want to fix a bug. This functionality is not implemented yet.")
    elif intent == "code_refactor":
        print("You want to refactor code. This functionality is not implemented yet.")
    elif intent == "ideation":
        ideation()
    else:
        print("Your intent does not fit into any of the predefined categories. Please try again with a clearer intent.")


if __name__ == "__main__":
    main()
