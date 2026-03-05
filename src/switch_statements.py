"""Switch Statements detector for Python source files.

Two heuristics are applied:

    IfElseChain
        An if/elif chain with `if_else_chain_threshold` or more total branches
        (the `if` branch counts as one, each `elif` adds one more). Long
        conditional chains on type codes should be replaced with polymorphism
        or a dispatch table.

    ComplexMatch
        A match statement with `match_case_threshold` or more case clauses.
        Complex type-code dispatch via match should be replaced with
        polymorphism.

Thresholds:
    if_else_chain_threshold  default: 3
    match_case_threshold     default: 3
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_IF_ELSE = "SwitchStatement.IfElseChain"
_SMELL_MATCH = "SwitchStatement.ComplexMatch"

_DEFAULT_IF_ELSE_THRESHOLD = 3
_DEFAULT_MATCH_THRESHOLD = 3

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


def detect(
    path: str | Path,
    if_else_chain_threshold: int = _DEFAULT_IF_ELSE_THRESHOLD,
    match_case_threshold: int = _DEFAULT_MATCH_THRESHOLD,
) -> list[SmellReport]:
    """Return all Switch Statement smells found in the Python file at `path`.

    Args:
        path: Path to a Python source file.
        if_else_chain_threshold: Flag if/elif chains with this many or more
                                 total branches (if + elif count).
        match_case_threshold:    Flag match statements with this many or more
                                 case clauses.

    Returns:
        A list of SmellReport. Empty when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If any threshold is less than 2.
    """
    for tname, value in [
        ("if_else_chain_threshold", if_else_chain_threshold),
        ("match_case_threshold", match_case_threshold),
    ]:
        if value < 2:
            raise ValueError(f"{tname} must be >= 2, got {value}")

    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    path_str = str(path)

    reports: list[SmellReport] = []
    _walk(
        tree.root_node, path_str,
        if_else_chain_threshold, match_case_threshold,
        "<module>", reports,
    )
    return reports


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------

def _walk(
    node: Node,
    path: str,
    threshold_if: int,
    threshold_match: int,
    scope: str,
    reports: list[SmellReport],
) -> None:
    node_type = node.type

    # Update scope on entry to a function or class definition.
    current_scope = scope
    if node_type in ("function_definition", "async_function_definition"):
        name_node = node.child_by_field_name("name")
        if name_node:
            current_scope = name_node.text.decode()
    elif node_type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            current_scope = name_node.text.decode()

    if node_type == "if_statement":
        elif_count = sum(1 for c in node.children if c.type == "elif_clause")
        branch_count = 1 + elif_count
        if branch_count >= threshold_if:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            reports.append(SmellReport(
                smell=_SMELL_IF_ELSE,
                file=path,
                name=current_scope,
                start_line=start_line,
                end_line=end_line,
                line_count=end_line - start_line + 1,
                branch_count=branch_count,
                message=(
                    f"if/elif chain has {branch_count} branches"
                    f" (threshold: {threshold_if})."
                    " Consider replacing with polymorphism or a dispatch table."
                ),
            ))

    elif node_type == "match_statement":
        # case_clause nodes live inside a nested block child of match_statement
        block = next((c for c in node.children if c.type == "block"), None)
        case_count = sum(1 for c in block.children if c.type == "case_clause") if block else 0
        if case_count >= threshold_match:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            reports.append(SmellReport(
                smell=_SMELL_MATCH,
                file=path,
                name=current_scope,
                start_line=start_line,
                end_line=end_line,
                line_count=end_line - start_line + 1,
                branch_count=case_count,
                message=(
                    f"match statement has {case_count} cases"
                    f" (threshold: {threshold_match})."
                    " Consider replacing with polymorphism."
                ),
            ))

    for child in node.children:
        _walk(child, path, threshold_if, threshold_match, current_scope, reports)
