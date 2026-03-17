import os
import shlex
import subprocess
import tempfile

_TEMPLATE = """\
# Title

- Tags:

## Why
- Problem: {The problem to resolve with this project.}
- Hypothesis: {The hypothesis of this requirement to resolve problem.}
- Expect: {The expected result of this requirement.}

## What
- Input: {The trigger point or input data to handle this requirement.}
- Process: {The functionality to process this requirement.}
- Output: {The output data or result of this requirement.}

## How
- Constraints: {The previous system, polish, technical constraints.}
- Approach: {The big picture of logic flow or data flow.}
- Acceptance Criteria: {The acceptance criteria of this requirement.}

## Related RS
"""


def open_editor(initial_content: str | None = None, available_tags: list[str] | None = None) -> str:
    """Open the user's preferred editor with a requirement template or existing content.

    When available_tags is provided, a hint listing existing tags is injected
    immediately before the "- Tags:" line so the user can reuse them. The hint
    is an HTML comment and is ignored by the requirement parser.

    Guarantees: returns the full file contents after the editor closes.
    Assumes: $EDITOR or vi is available on PATH.
    Fails: raises OSError if the editor process fails or the temp file is unreadable.
    """
    editor = os.environ.get("EDITOR", "vi")
    content = initial_content if initial_content is not None else _TEMPLATE
    if available_tags:
        hint = f"<!-- Available tags: {', '.join(available_tags)} -->\n"
        content = content.replace("- Tags:", hint + "- Tags:", 1)
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        result = subprocess.run([*shlex.split(editor), tmp_path])
        if result.returncode != 0:
            raise OSError(f"Editor exited with code {result.returncode}.")
        with open(tmp_path) as f:
            return f.read()
    finally:
        os.unlink(tmp_path)
