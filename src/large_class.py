"""Large Class detector for Python source files.

A class is a Large Class when it exceeds at least one of these thresholds:
    - line_count  > line_threshold    (default: 200) — total physical lines
    - method_count > method_threshold  (default: 20)  — number of methods
    - field_count  > field_threshold   (default: 10)  — unique instance/class fields

Counting rules:
    - method_count: counts every def inside the class body (including static/class
      methods and decorated definitions), but NOT nested functions inside methods.
    - field_count: counts unique `self.X` assignment targets across all methods,
      plus class-level variable assignments/annotations in the class body.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_NAME = "LargeClass"
_DEFAULT_LINE_THRESHOLD = 200
_DEFAULT_METHOD_THRESHOLD = 20
_DEFAULT_FIELD_THRESHOLD = 10

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


def detect(
    path: str | Path,
    line_threshold: int = _DEFAULT_LINE_THRESHOLD,
    method_threshold: int = _DEFAULT_METHOD_THRESHOLD,
    field_threshold: int = _DEFAULT_FIELD_THRESHOLD,
) -> list[SmellReport]:
    """Return all Large Class smells found in the Python file at `path`.

    Args:
        path: Path to a Python source file.
        line_threshold:   Flag classes with more physical lines than this value.
        method_threshold: Flag classes with more methods than this value.
        field_threshold:  Flag classes with more unique fields than this value.

    Returns:
        A list of SmellReport, one per class that exceeds any threshold.
        Empty list when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If any threshold is less than 1.
    """
    for name, value in [
        ("line_threshold", line_threshold),
        ("method_threshold", method_threshold),
        ("field_threshold", field_threshold),
    ]:
        if value < 1:
            raise ValueError(f"{name} must be >= 1, got {value}")

    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    reports = []

    for class_node in _iter_classes(tree.root_node):
        class_name = _node_name(class_node)
        body = class_node.child_by_field_name("body")
        if body is None:
            continue

        start_line = class_node.start_point[0] + 1
        end_line = class_node.end_point[0] + 1
        line_count = end_line - start_line + 1
        method_count = _count_methods(body)
        field_count = _count_fields(body)

        triggered = []
        if line_count > line_threshold:
            triggered.append(f"{line_count} lines (threshold: {line_threshold})")
        if method_count > method_threshold:
            triggered.append(
                f"{method_count} methods (threshold: {method_threshold})"
            )
        if field_count > field_threshold:
            triggered.append(
                f"{field_count} fields (threshold: {field_threshold})"
            )

        if not triggered:
            continue

        reports.append(
            SmellReport(
                smell=_SMELL_NAME,
                file=str(path),
                name=class_name,
                start_line=start_line,
                end_line=end_line,
                line_count=line_count,
                method_count=method_count,
                field_count=field_count,
                message=f"Class '{class_name}' is too large: {', '.join(triggered)}.",
            )
        )

    return reports


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_classes(node: Node):
    """Yield every top-level and nested class_definition node."""
    if node.type == "class_definition":
        yield node
    for child in node.children:
        yield from _iter_classes(child)


def _node_name(node: Node) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return name_node.text.decode("utf-8")


def _count_methods(class_body: Node) -> int:
    """Count direct method definitions in a class body.

    Counts function_definition and decorated_definition (where the inner
    definition is a function) as one method each. Nested functions inside
    method bodies are not counted.
    """
    count = 0
    for child in class_body.children:
        if child.type == "function_definition":
            count += 1
        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner and inner.type == "function_definition":
                count += 1
    return count


def _count_fields(class_body: Node) -> int:
    """Count unique field names: class-level assignments + self.X assignments."""
    names: set[str] = set()

    # Class-level variable assignments and annotations.
    for child in class_body.children:
        if child.type == "expression_statement":
            for inner in child.children:
                if inner.type == "assignment":
                    left = inner.child_by_field_name("left")
                    _collect_simple_names(left, names)
                elif inner.type == "augmented_assignment":
                    left = inner.child_by_field_name("left")
                    _collect_simple_names(left, names)
        elif child.type == "annotated_assignment":
            left = child.child_by_field_name("left")
            _collect_simple_names(left, names)

    # Instance attributes: self.X = ... inside methods.
    for child in class_body.children:
        method_node = None
        if child.type == "function_definition":
            method_node = child
        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner and inner.type == "function_definition":
                method_node = inner

        if method_node is not None:
            _collect_self_attrs(method_node, names)

    return len(names)


def _collect_simple_names(node: Node | None, names: set[str]) -> None:
    """Add identifier names from a simple assignment left-hand side."""
    if node is None:
        return
    if node.type == "identifier":
        names.add(node.text.decode("utf-8"))
    elif node.type in ("tuple", "pattern_list"):
        for child in node.children:
            _collect_simple_names(child, names)


def _collect_self_attrs(method_node: Node, names: set[str]) -> None:
    """Walk a method body and collect all self.X assignment targets."""
    body = method_node.child_by_field_name("body")
    if body is None:
        return
    _walk_self_assignments(body, names, depth=0)


def _walk_self_assignments(node: Node, names: set[str], depth: int) -> None:
    # Do not descend into nested function/class definitions.
    if depth > 0 and node.type in ("function_definition", "class_definition"):
        return

    if node.type in ("assignment", "augmented_assignment"):
        left = node.child_by_field_name("left")
        _check_self_attr(left, names)
    elif node.type == "annotated_assignment":
        left = node.child_by_field_name("left")
        _check_self_attr(left, names)

    for child in node.children:
        _walk_self_assignments(child, names, depth + 1)


def _check_self_attr(node: Node | None, names: set[str]) -> None:
    if node is None or node.type != "attribute":
        return
    obj = node.child_by_field_name("object")
    attr = node.child_by_field_name("attribute")
    if (
        obj is not None
        and obj.type == "identifier"
        and obj.text == b"self"
        and attr is not None
    ):
        names.add(attr.text.decode("utf-8"))
