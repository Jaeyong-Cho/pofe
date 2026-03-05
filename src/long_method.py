"""Long Method detector for Python source files.

A function is a Long Method when its physical line count exceeds `threshold`.
Physical lines = all lines from `def` to the last line of the body,
including blank lines and inline comments.

Threshold default: 20 lines (configurable per call).
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_NAME = "LongMethod"
_DEFAULT_THRESHOLD = 20

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


def detect(path: str | Path, threshold: int = _DEFAULT_THRESHOLD) -> list[SmellReport]:
    """Return all Long Method smells found in the Python file at `path`.

    Args:
        path: Path to a Python source file.
        threshold: Minimum physical line count to flag as a Long Method.

    Returns:
        A list of SmellReport, one per function that exceeds `threshold`.
        Empty list when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If `threshold` is less than 1.
    """
    if threshold < 1:
        raise ValueError(f"threshold must be >= 1, got {threshold}")

    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    reports = []

    for func_node in _iter_functions(tree.root_node):
        start_line = func_node.start_point[0] + 1
        end_line = func_node.end_point[0] + 1
        line_count = end_line - start_line + 1

        if line_count > threshold:
            name = _function_name(func_node)
            reports.append(
                SmellReport(
                    smell=_SMELL_NAME,
                    file=str(path),
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    line_count=line_count,
                    message=(
                        f"Function '{name}' has {line_count} lines"
                        f" (threshold: {threshold})."
                    ),
                )
            )

    return reports


def _iter_functions(node: Node):
    """Yield every function_definition node in the subtree rooted at `node`."""
    if node.type == "function_definition":
        yield node
    for child in node.children:
        yield from _iter_functions(child)


def _function_name(node: Node) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return name_node.text.decode("utf-8")
