"""Data Clumps detector for Python source files.

Two heuristics are applied:

    ParameterClump
        Two or more functions share a group of min_clump_size+ parameter names.
        These shared parameters should be encapsulated in a parameter object.

    FieldClump
        Two or more classes share a group of min_clump_size+ field names.
        These shared fields should be extracted into their own class.

Default min_clump_size: 3

Cross-file detection is supported via collect_param_data() / collect_field_data()
+ detect_from_collected(). detect_smells() in __init__.py uses this path.
detect() on a single file is available for per-file use and testing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_PARAM_CLUMP = "DataClump.ParameterClump"
_SMELL_FIELD_CLUMP = "DataClump.FieldClump"
_DEFAULT_MIN_CLUMP_SIZE = 3

_SKIP_PARAM_NAMES = frozenset({"self", "cls"})

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


# ---------------------------------------------------------------------------
# Intermediate data types (opaque outside this module)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FuncData:
    name: str
    file: str
    start_line: int
    end_line: int
    params: frozenset


@dataclass(frozen=True)
class _ClassData:
    name: str
    file: str
    start_line: int
    end_line: int
    fields: frozenset


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect(
    path: str | Path,
    min_clump_size: int = _DEFAULT_MIN_CLUMP_SIZE,
) -> list[SmellReport]:
    """Return all Data Clump smells found within `path` (single-file).

    Args:
        path: Path to a Python source file.
        min_clump_size: Minimum number of shared names to constitute a clump.
                        Must be >= 2.

    Returns:
        A list of SmellReport. Empty when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If min_clump_size is less than 2.
    """
    _validate(min_clump_size)
    param_data = collect_param_data(path)
    field_data = collect_field_data(path)
    return detect_from_collected(param_data, field_data, min_clump_size)


def collect_param_data(path: str | Path) -> list:
    """Parse `path` and return one record per function with its parameter names.

    The records are opaque; pass them to detect_from_collected().

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    result = []
    for func_node in _iter_functions(tree.root_node):
        params_node = func_node.child_by_field_name("parameters")
        if params_node is None:
            continue
        params = _extract_param_names(params_node)
        if len(params) >= 2:
            result.append(_FuncData(
                name=_node_name(func_node),
                file=str(path),
                start_line=func_node.start_point[0] + 1,
                end_line=func_node.end_point[0] + 1,
                params=params,
            ))
    return result


def collect_field_data(path: str | Path) -> list:
    """Parse `path` and return one record per class with its field names.

    The records are opaque; pass them to detect_from_collected().

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    result = []
    for class_node in _iter_classes(tree.root_node):
        body = class_node.child_by_field_name("body")
        if body is None:
            continue
        fields = _collect_field_names(body)
        if len(fields) >= 2:
            result.append(_ClassData(
                name=_node_name(class_node),
                file=str(path),
                start_line=class_node.start_point[0] + 1,
                end_line=class_node.end_point[0] + 1,
                fields=fields,
            ))
    return result


def detect_from_collected(
    param_data: list,
    field_data: list,
    min_clump_size: int = _DEFAULT_MIN_CLUMP_SIZE,
) -> list[SmellReport]:
    """Detect data clumps from pre-collected data (supports cross-file detection).

    Args:
        param_data: Output of one or more collect_param_data() calls.
        field_data: Output of one or more collect_field_data() calls.
        min_clump_size: Minimum shared names to constitute a clump. Must be >= 2.

    Returns:
        A list of SmellReport. Empty when no smells are found.

    Raises:
        ValueError: If min_clump_size is less than 2.
    """
    _validate(min_clump_size)
    reports = []
    reports.extend(_find_clumps(param_data, min_clump_size, _SMELL_PARAM_CLUMP, "parameter", "parameter object"))
    reports.extend(_find_clumps(field_data, min_clump_size, _SMELL_FIELD_CLUMP, "field", "shared class"))
    return reports


# ---------------------------------------------------------------------------
# Internal detection
# ---------------------------------------------------------------------------


def _validate(min_clump_size: int) -> None:
    if min_clump_size < 2:
        raise ValueError(f"min_clump_size must be >= 2, got {min_clump_size}")


def _find_clumps(
    items: list,
    min_clump_size: int,
    smell_name: str,
    group_label: str,
    fix_label: str,
) -> list[SmellReport]:
    n = len(items)
    # clump frozenset -> list of item indices
    clump_to_indices: dict[frozenset, list[int]] = defaultdict(list)

    for i in range(n):
        for j in range(i + 1, n):
            common = items[i].params if hasattr(items[i], "params") else items[i].fields
            other = items[j].params if hasattr(items[j], "params") else items[j].fields
            common = common & other
            if len(common) >= min_clump_size:
                clump_to_indices[common].append(i)
                clump_to_indices[common].append(j)

    reports = []
    seen: set[tuple] = set()

    for clump, indices in clump_to_indices.items():
        # Deduplicate participant list while preserving order
        seen_locs: set[tuple] = set()
        participants = []
        for idx in indices:
            loc = (items[idx].file, items[idx].start_line)
            if loc not in seen_locs:
                seen_locs.add(loc)
                participants.append(items[idx])

        clump_tuple = tuple(sorted(clump))

        for item in participants:
            report_key = (item.file, item.start_line, clump)
            if report_key in seen:
                continue
            seen.add(report_key)

            others = [p for p in participants if p is not item]
            other_labels = [
                f"{p.name} ({p.file}:{p.start_line})" if p.file != item.file else p.name
                for p in others
            ]
            reports.append(SmellReport(
                smell=smell_name,
                file=item.file,
                name=item.name,
                start_line=item.start_line,
                end_line=item.end_line,
                line_count=item.end_line - item.start_line + 1,
                clump=clump_tuple,
                message=(
                    f"'{item.name}' shares {group_label} group"
                    f" ({', '.join(clump_tuple)}) with: {', '.join(other_labels)}."
                    f" Consider introducing a {fix_label}."
                ),
            ))

    return reports


# ---------------------------------------------------------------------------
# Parameter name extraction
# ---------------------------------------------------------------------------


def _extract_param_names(params_node: Node) -> frozenset:
    names: set[str] = set()
    for child in params_node.children:
        name: str | None = None
        if child.type == "identifier":
            name = child.text.decode("utf-8")
        elif child.type in ("typed_default_parameter", "default_parameter"):
            name_node = child.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
        elif child.type == "typed_parameter":
            for sub in child.children:
                if sub.type == "identifier":
                    name = sub.text.decode("utf-8")
                    break
        if name and name not in _SKIP_PARAM_NAMES:
            names.add(name)
    return frozenset(names)


# ---------------------------------------------------------------------------
# Field name extraction
# ---------------------------------------------------------------------------


def _collect_field_names(class_body: Node) -> frozenset:
    names: set[str] = set()

    for child in class_body.children:
        # Class-level assignments: X = ...
        if child.type == "expression_statement":
            for inner in child.children:
                if inner.type == "assignment":
                    left = inner.child_by_field_name("left")
                    if left and left.type == "identifier":
                        names.add(left.text.decode("utf-8"))
        # Class-level annotated assignments: X: type [= ...]
        elif child.type == "annotated_assignment":
            left = child.child_by_field_name("left")
            if left and left.type == "identifier":
                names.add(left.text.decode("utf-8"))

    # Instance attributes from self.X = ... in methods (not nested functions)
    for child in class_body.children:
        method_node = None
        if child.type == "function_definition":
            method_node = child
        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner and inner.type == "function_definition":
                method_node = inner
        if method_node is not None:
            body = method_node.child_by_field_name("body")
            if body:
                _walk_self_assignments(body, names, depth=0)

    return frozenset(names)


def _walk_self_assignments(node: Node, names: set[str], depth: int) -> None:
    if depth > 0 and node.type in ("function_definition", "class_definition"):
        return
    if node.type in ("assignment", "augmented_assignment", "annotated_assignment"):
        left = node.child_by_field_name("left")
        if left and left.type == "attribute":
            obj = left.child_by_field_name("object")
            attr = left.child_by_field_name("attribute")
            if obj and obj.type == "identifier" and obj.text == b"self" and attr:
                names.add(attr.text.decode("utf-8"))
    for child in node.children:
        _walk_self_assignments(child, names, depth + 1)


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
