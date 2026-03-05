"""Temporary Field detector for Python source files.

Heuristic: TemporaryField

    A class has instance fields (`self.X`) that carry state only during the
    execution of one specific method. Outside that method the field is
    meaningless (typically None or unset). This fragments understanding: a
    reader must track which methods are "active" to know what the object's
    fields mean.

    Two patterns are detected:

        Pure temp
            `self.field` is NEVER assigned in `__init__`; it is assigned in
            exactly one non-constructor method (the "algorithm" method); and it
            is read in at least one other method.

        Init-None temp
            `self.field = None` is the only assignment in `__init__` (a bare
            placeholder); a real value is assigned in exactly one other method;
            and at least one different method reads it.

    The fix is typically Extract Class / Method Object: move the algorithm and
    its transient fields into a dedicated class.

Default threshold: 1  (flag class when >= 1 temporary field is found)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterator

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL = "TemporaryField"
_DEFAULT_THRESHOLD = 1

_CONSTRUCTOR_NAMES = frozenset({"__init__", "__new__"})

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


def detect(
    path: str | Path,
    threshold: int = _DEFAULT_THRESHOLD,
) -> list[SmellReport]:
    """Return all Temporary Field smells found in the Python file at `path`.

    Args:
        path:      Path to a Python source file.
        threshold: Minimum number of temporary fields required to flag a class.

    Returns:
        A list of SmellReport, one per class that has enough temp fields.
        Empty when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If threshold is less than 1.
    """
    if threshold < 1:
        raise ValueError(f"threshold must be >= 1, got {threshold}")

    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    path_str = str(path)

    reports: list[SmellReport] = []
    for class_node in _iter_classes(tree.root_node):
        report = _analyze_class(class_node, path_str, threshold)
        if report is not None:
            reports.append(report)
    return reports


# ---------------------------------------------------------------------------
# Class analysis
# ---------------------------------------------------------------------------

def _analyze_class(class_node: Node, path: str, threshold: int) -> SmellReport | None:
    body = class_node.child_by_field_name("body")
    if body is None:
        return None

    methods = _collect_methods(body)
    if not methods:
        return None

    # field -> set of method names that write / read it
    field_writers: dict[str, set[str]] = defaultdict(set)
    field_readers: dict[str, set[str]] = defaultdict(set)
    # fields written to None in any constructor
    init_none_fields: set[str] = set()

    for method_name, method_node in methods:
        writes, reads = _collect_field_accesses(method_node)
        for fname in writes:
            field_writers[fname].add(method_name)
        for fname in reads:
            field_readers[fname].add(method_name)
        if method_name in _CONSTRUCTOR_NAMES:
            init_none_fields.update(_find_none_assigned_fields(method_node))

    temp_fields: list[str] = []
    for fname in sorted(field_writers):
        writers = field_writers[fname]
        readers = field_readers.get(fname, set())
        non_ctor_writers = writers - _CONSTRUCTOR_NAMES

        # Must be written in exactly one non-constructor method
        if len(non_ctor_writers) != 1:
            continue
        writer = next(iter(non_ctor_writers))

        # Constructor may not write it, OR may only write None to it
        if writers & _CONSTRUCTOR_NAMES and fname not in init_none_fields:
            continue  # constructor establishes a real value; not a temp field

        # Must be read in at least one method that is not the single writer
        if not (readers - {writer}):
            continue

        temp_fields.append(fname)

    if len(temp_fields) < threshold:
        return None

    name_node = class_node.child_by_field_name("name")
    class_name = name_node.text.decode() if name_node else "<anonymous>"
    start_line = class_node.start_point[0] + 1
    end_line = class_node.end_point[0] + 1
    fields_str = ", ".join(f"'{f}'" for f in temp_fields)
    plural = "field" if len(temp_fields) == 1 else "fields"
    return SmellReport(
        smell=_SMELL,
        file=path,
        name=class_name,
        start_line=start_line,
        end_line=end_line,
        line_count=end_line - start_line + 1,
        temp_fields=tuple(temp_fields),
        message=(
            f"Class '{class_name}' has {len(temp_fields)} temporary {plural}:"
            f" {fields_str}."
            " These fields are set only in specific methods and meaningless"
            " otherwise. Consider extracting them into a dedicated class"
            " (Method Object)."
        ),
    )


# ---------------------------------------------------------------------------
# Method collection
# ---------------------------------------------------------------------------

def _collect_methods(class_body: Node) -> list[tuple[str, Node]]:
    """Return (name, function_node) for every method in the class body."""
    methods: list[tuple[str, Node]] = []
    for child in class_body.children:
        func = None
        if child.type in ("function_definition", "async_function_definition"):
            func = child
        elif child.type == "decorated_definition":
            inner = child.child_by_field_name("definition")
            if inner and inner.type in ("function_definition", "async_function_definition"):
                func = inner
        if func is not None:
            name_node = func.child_by_field_name("name")
            if name_node:
                methods.append((name_node.text.decode(), func))
    return methods


# ---------------------------------------------------------------------------
# Field access collection
# ---------------------------------------------------------------------------

def _collect_field_accesses(method_node: Node) -> tuple[set[str], set[str]]:
    """Return (writes, reads) of `self.X` fields within the method body.

    Does not descend into nested function or class definitions.
    """
    body = method_node.child_by_field_name("body")
    if body is None:
        return set(), set()
    writes: set[str] = set()
    reads: set[str] = set()
    _walk_accesses(body, writes, reads)
    return writes, reads


def _walk_accesses(node: Node, writes: set[str], reads: set[str]) -> None:
    if node.type in (
        "function_definition", "async_function_definition", "class_definition"
    ):
        return

    if node.type == "attribute":
        obj = node.child_by_field_name("object")
        attr = node.child_by_field_name("attribute")
        if (
            obj is not None
            and obj.type == "identifier"
            and obj.text == b"self"
            and attr is not None
        ):
            field_name = attr.text.decode()
            parent = node.parent
            if parent is not None and parent.type in (
                "assignment", "augmented_assignment"
            ):
                left = parent.child_by_field_name("left")
                if left == node:
                    writes.add(field_name)
                    return
            reads.add(field_name)
            return

    for child in node.children:
        _walk_accesses(child, writes, reads)


def _find_none_assigned_fields(method_node: Node) -> set[str]:
    """Return names of `self.X` fields assigned to `None` in this method."""
    body = method_node.child_by_field_name("body")
    if body is None:
        return set()
    result: set[str] = set()
    _walk_none_assigns(body, result)
    return result


def _walk_none_assigns(node: Node, result: set[str]) -> None:
    if node.type in (
        "function_definition", "async_function_definition", "class_definition"
    ):
        return
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is not None and right is not None and right.type == "none":
            if left.type == "attribute":
                obj = left.child_by_field_name("object")
                attr = left.child_by_field_name("attribute")
                if (
                    obj is not None
                    and obj.type == "identifier"
                    and obj.text == b"self"
                    and attr is not None
                ):
                    result.add(attr.text.decode())
    for child in node.children:
        _walk_none_assigns(child, result)


# ---------------------------------------------------------------------------
# Class iteration
# ---------------------------------------------------------------------------

def _iter_classes(node: Node) -> Iterator[Node]:
    """Yield every class_definition node, including nested ones."""
    if node.type == "class_definition":
        yield node
    for child in node.children:
        yield from _iter_classes(child)
