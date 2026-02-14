"""
Shared AI model interface.

Provides a unified way to call different AI backends (Copilot CLI, Ollama)
so that all services use the same calling convention without coupling to
a specific backend.
"""

import subprocess
import sys
import json
from typing import Callable


def ask_copilot(prompt: str, model: str = "gpt-4.1") -> str:
    """
    Send a prompt to Copilot CLI and return the response.

    Assumes the 'copilot' command is installed and available on PATH.
    """
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
    """
    Send a prompt to a local Ollama model and return the response.

    Requires the 'ollama' Python package to be installed.
    """
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


def ask_ai(prompt: str, backend: str = "copilot", model: str | None = None) -> str:
    """
    Unified AI query interface.

    Args:
        prompt:  The prompt to send.
        backend: "copilot" or "ollama".
        model:   Model name override (uses backend default when None).

    Returns:
        The AI model's response text.
    """
    if backend == "copilot":
        return ask_copilot(prompt, model=model or "gpt-4.1")
    elif backend == "ollama":
        return ask_ollama(prompt, model=model or "qwen3:14b")
    else:
        raise ValueError(f"Unknown AI backend: {backend}")


def ask_ai_json(prompt: str, backend: str = "copilot", model: str | None = None) -> dict:
    """
    Query AI and parse the response as JSON.

    Raises ValueError if the response is not valid JSON.
    """
    raw = ask_ai(prompt, backend=backend, model=model)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI response is not valid JSON: {e}\nResponse: {raw}")
