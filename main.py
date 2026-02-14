import subprocess
import sys
import json


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


def ask_ollama(prompt: str, model: str = "llama3.1:8b") -> str:
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
            ]
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

def main():
    print("Welcome to pofe - Source Code Understanding Tool!")

    understand_project()


if __name__ == "__main__":
    main()
