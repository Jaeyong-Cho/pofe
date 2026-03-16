import os
import shlex
import subprocess
import tempfile

_TEMPLATE = """\
# Title

## Why
- Problem:
- Hypothesis:
- Expect:

## What
- Input:
- Process:
- Output:

## How
- Constraints:
- Approach:
- Acceptance Criteria:
"""


def open_editor() -> str:
    """Open the user's preferred editor with a blank requirement template.

    Guarantees: returns the full file contents after the editor closes.
    Assumes: $EDITOR or vi is available on PATH.
    Fails: raises OSError if the editor process fails or the temp file is unreadable.
    """
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(_TEMPLATE)
        tmp_path = f.name
    try:
        result = subprocess.run([*shlex.split(editor), tmp_path])
        if result.returncode != 0:
            raise OSError(f"Editor exited with code {result.returncode}.")
        with open(tmp_path) as f:
            return f.read()
    finally:
        os.unlink(tmp_path)
