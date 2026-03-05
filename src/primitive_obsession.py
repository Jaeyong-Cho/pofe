"""Primitive Obsession detector for Python source files.

Two heuristics are applied:

    TypeCode
        A class body or module scope contains `type_code_threshold` or more
        ALL_CAPS assignments to primitive literals (int, str, float, bool).
        This indicates type codes implemented with raw constants instead of
        enums or proper value objects.

    PrimitiveParameterCluster
        A function or method has `primitive_param_threshold` or more parameters
        with primitive type annotations (int, str, float, bool, bytes).
        This indicates a missing parameter object.

Thresholds:
    type_code_threshold       default: 3
    primitive_param_threshold default: 5
"""

from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_TYPE_CODE = "PrimitiveObsession.TypeCode"
_SMELL_PRIM_PARAM = "PrimitiveObsession.PrimitiveParameterCluster"

_DEFAULT_TYPE_CODE_THRESHOLD = 3
_DEFAULT_PRIM_PARAM_THRESHOLD = 5

_PRIMITIVE_TYPES = frozenset({"int", "str", "float", "bool", "bytes"})
_PRIMITIVE_LITERALS = frozenset({
    "integer", "float", "string", "true", "false", "none", "concatenated_string",
})
_ALLCAPS_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


def detect(
    path: str | Path,
    type_code_threshold: int = _DEFAULT_TYPE_CODE_THRESHOLD,
    primitive_param_threshold: int = _DEFAULT_PRIM_PARAM_THRESHOLD,
) -> list[SmellReport]:
    """Return all Primitive Obsession smells found in the Python file at `path`.

    Args:
        path: Path to a Python source file.
        type_code_threshold:       Flag scopes with this many or more ALL_CAPS
                                   primitive constants.
        primitive_param_threshold: Flag functions with this many or more
                                   primitive-typed parameters.

    Returns:
        A list of SmellReport. Empty when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If any threshold is less than 1.
    """
    for tname, value in [
        ("type_code_threshold", type_code_threshold),
        ("primitive_param_threshold", primitive_param_threshold),
    ]:
        if value < 1:
            raise ValueError(f"{tname} must be >= 1, got {value}")

    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    path_str = str(path)

    reports = []
    reports.extend(_detect_type_codes(tree.root_node, path_str, type_code_threshold))
    reports.extend(_detect_primitive_params(tree.root_node, path_str, primitive_param_threshold))
    return reports


# ---------------------------------------------------------------------------
# Type code detection
# ---------------------------------------------------------------------------

def _detect_type_codes(root: Node, path: str, threshold: int) -> list[SmellReport]:
    reports = []

    # Module-level constants
    constants = _collect_type_code_positions(root)
    if len(constants) >= threshold:
        first_line = constants[0][1]
        last_line = constants[-1][1]
        count = len(constants)
        reports.append(SmellReport(
            smell=_SMELL_TYPE_CODE,
            file=path,
            name="<module>",
            start_line=first_line,
            end_line=last_line,
            line_count=last_line - first_line + 1,
            primitive_count=count,
            message=(
                f"Module scope has {count} ALL_CAPS primitive constants"
                f" (threshold: {threshold})."
                " Consider using an Enum or value object."
            ),
        ))

    # Class-level constants
    for class_node in _iter_classes(root):
        body = class_node.child_by_field_name("body")
        if body is None:
            continue
        constants = _collect_type_code_positions(body)
        if len(constants) >= threshold:
            class_name = _node_name(class_node)
            count = len(constants)
            reports.append(SmellReport(
                smell=_SMELL_TYPE_CODE,
                file=path,
                name=class_name,
                start_line=class_node.start_point[0] + 1,
                end_line=class_node.end_point[0] + 1,
                line_count=class_node.end_point[0] - class_node.start_point[0] + 1,
                primitive_count=count,
                message=(
                    f"Class '{class_name}' has {count} ALL_CAPS primitive constants"
                    f" (threshold: {threshold})."
                    " Consider using an Enum or value object."
                ),
            ))

    return reports


def _collect_type_code_positions(node: Node) -> list[tuple[str, int]]:
    """Return (name, 1-based line) for ALL_CAPS primitive constants in direct children."""
    results = []
    for child in node.children:
        if child.type == "expression_statement":
            for inner in child.children:
                if inner.type == "assignment":
                    left = inner.child_by_field_name("left")
                    right = inner.child_by_field_name("right")
                    if _is_allcaps_identifier(left) and _is_primitive_literal(right):
                        results.append((
                            left.text.decode("utf-8"),
                            left.start_point[0] + 1,
                        ))
    return results


def _is_allcaps_identifier(node: Node | None) -> bool:
    if node is None or node.type != "identifier":
        return False
    return bool(_ALLCAPS_RE.match(node.text.decode("utf-8")))


def _is_primitive_literal(node: Node | None) -> bool:
    return node is not None and node.type in _PRIMITIVE_LITERALS


# ---------------------------------------------------------------------------
# Primitive parameter cluster detection
# ---------------------------------------------------------------------------

def _detect_primitive_params(root: Node, path: str, threshold: int) -> list[SmellReport]:
    reports = []
    for func_node in _iter_functions(root):
        params_node = func_node.child_by_field_name("parameters")
        if params_node is None:
            continue
        count = _count_primitive_typed_params(params_node)
        if count >= threshold:
            name = _node_name(func_node)
            start_line = func_node.start_point[0] + 1
            end_line = func_node.end_point[0] + 1
            reports.append(SmellReport(
                smell=_SMELL_PRIM_PARAM,
                file=path,
                name=name,
                start_line=start_line,
                end_line=end_line,
                line_count=end_line - start_line + 1,
                primitive_count=count,
                message=(
                    f"Function '{name}' has {count} primitive-typed parameters"
                    f" (threshold: {threshold})."
                    " Consider introducing a parameter object."
                ),
            ))
    return reports


def _count_primitive_typed_params(params_node: Node) -> int:
    count = 0
    for child in params_node.children:
        if child.type in ("typed_parameter", "typed_default_parameter"):
            type_node = child.child_by_field_name("type")
            if type_node is None:
                continue
            # The "type" field is a `type` node wrapping an identifier.
            # Walk into it to find the actual name.
            name_node = (
                type_node
                if type_node.type == "identifier"
                else type_node.child(0)
            )
            if (
                name_node is not None
                and name_node.type == "identifier"
                and name_node.text.decode("utf-8") in _PRIMITIVE_TYPES
            ):
                count += 1
    return count


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def _iter_functions(node: Node):
    if node.type == "function_definition":
        yield node
    for child in node.children:
        yield from _iter_functions(child)


def _iter_classes(node: Node):
    if node.type == "class_definition":
        yield node
    for child in node.children:
        yield from _iter_classes(child)


def _node_name(node: Node) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return "<anonymous>"
    return name_node.text.decode("utf-8")
