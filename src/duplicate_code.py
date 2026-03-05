"""Duplicate Code detector for Python source files.

Two heuristics:

    ClonedFunction
        Two or more functions/methods have identical normalized bodies of
        min_lines or more effective (non-blank, non-comment) lines.
        Catches verbatim copy-paste of entire functions across the codebase.

    DuplicateBlock
        A run of min_block_stmts+ consecutive top-level statements appears
        verbatim (normalized) in two or more different functions/methods.
        Catches partial copy-paste where only a section was duplicated.

Normalization for both heuristics:
    - Strip common leading indentation from all lines.
    - Drop blank lines and comment-only lines.
    - Inline comments are NOT stripped (modifying comments can change meaning).

Cross-file detection is supported via collect_body_data() +
detect_from_collected(). detect_smells() in __init__.py uses this path.
detect() on a single file is available for per-file use and testing.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from .models import SmellReport

_SMELL_CLONE = "DuplicateCode.ClonedFunction"
_SMELL_BLOCK = "DuplicateCode.DuplicateBlock"

_DEFAULT_MIN_LINES = 3
_DEFAULT_MIN_BLOCK_STMTS = 3

_SKIP_NODE_TYPES = frozenset({
    "comment", "newline", "indent", "dedent",
})

_PY_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_PY_LANGUAGE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(
    path: str | Path,
    min_lines: int = _DEFAULT_MIN_LINES,
    min_block_stmts: int = _DEFAULT_MIN_BLOCK_STMTS,
) -> list[SmellReport]:
    """Return all Duplicate Code smells found in the Python file at `path`.

    Args:
        path:             Path to a Python source file.
        min_lines:        Minimum effective lines for ClonedFunction to fire.
                          Prevents trivial one-liner functions from being reported.
        min_block_stmts:  Minimum consecutive statements for DuplicateBlock.

    Returns:
        A list of SmellReport. Empty when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If min_lines < 1 or min_block_stmts < 2.
    """
    body_data = collect_body_data(path)
    return detect_from_collected(
        body_data,
        min_lines=min_lines,
        min_block_stmts=min_block_stmts,
    )


def collect_body_data(path: str | Path) -> list["_FuncBodyData"]:
    """Extract normalized body data from every function in `path`.

    Returns an opaque list suitable for passing to detect_from_collected().

    Raises:
        FileNotFoundError: If `path` does not exist.
    """
    source = Path(path).read_bytes()
    tree = _PARSER.parse(source)
    result: list[_FuncBodyData] = []
    _collect_from_node(tree.root_node, source, str(path), result)
    return result


def detect_from_collected(
    body_data: list["_FuncBodyData"],
    *,
    min_lines: int = _DEFAULT_MIN_LINES,
    min_block_stmts: int = _DEFAULT_MIN_BLOCK_STMTS,
) -> list[SmellReport]:
    """Detect duplicate code across a pre-collected list of function body data.

    Args:
        body_data:       Output of one or more collect_body_data() calls.
        min_lines:       Minimum effective lines for ClonedFunction.
        min_block_stmts: Minimum consecutive statements for DuplicateBlock.

    Returns:
        A list of SmellReport. Empty when no duplicates are found.

    Raises:
        ValueError: If min_lines < 1 or min_block_stmts < 2.
    """
    if min_lines < 1:
        raise ValueError(f"min_lines must be >= 1, got {min_lines}")
    if min_block_stmts < 2:
        raise ValueError(f"min_block_stmts must be >= 2, got {min_block_stmts}")

    reports: list[SmellReport] = []
    reports.extend(_detect_cloned_functions(body_data, min_lines))
    reports.extend(_detect_duplicate_blocks(body_data, min_block_stmts))
    return reports


# ---------------------------------------------------------------------------
# Intermediate data type (opaque outside this module)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FuncBodyData:
    name: str
    file: str
    start_line: int
    end_line: int
    body_hash: str           # sha256 of normalized body text (for ClonedFunction)
    body_line_count: int     # effective (non-blank, non-comment) line count
    stmts: tuple             # tuple[str] — normalized text of each direct statement
    stmt_ranges: tuple       # tuple[(start_line, end_line)] per statement


# ---------------------------------------------------------------------------
# Collect function bodies from the AST
# ---------------------------------------------------------------------------

def _collect_from_node(
    node: Node,
    source: bytes,
    path: str,
    result: list[_FuncBodyData],
) -> None:
    if node.type in ("function_definition", "async_function_definition"):
        data = _build_func_data(node, source, path)
        if data is not None:
            result.append(data)
    for child in node.children:
        _collect_from_node(child, source, path, result)


def _build_func_data(
    func_node: Node, source: bytes, path: str
) -> _FuncBodyData | None:
    body = func_node.child_by_field_name("body")
    if body is None:
        return None

    name_node = func_node.child_by_field_name("name")
    name = name_node.text.decode("utf-8") if name_node else "<anonymous>"

    stmts: list[str] = []
    stmt_ranges: list[tuple[int, int]] = []

    for child in body.children:
        if child.type in _SKIP_NODE_TYPES:
            continue
        stmt_text = _normalize_stmt(child, source)
        if not stmt_text:
            continue
        stmts.append(stmt_text)
        stmt_ranges.append((child.start_point[0] + 1, child.end_point[0] + 1))

    if not stmts:
        return None

    normalized_body = "\n".join(stmts)
    body_hash = hashlib.sha256(normalized_body.encode()).hexdigest()
    body_line_count = normalized_body.count("\n") + 1

    return _FuncBodyData(
        name=name,
        file=path,
        start_line=func_node.start_point[0] + 1,
        end_line=func_node.end_point[0] + 1,
        body_hash=body_hash,
        body_line_count=body_line_count,
        stmts=tuple(stmts),
        stmt_ranges=tuple(stmt_ranges),
    )


def _normalize_stmt(node: Node, source: bytes) -> str:
    """Return normalized source text for a single statement node.

    Strips common leading indentation, removes blank lines and comment-only lines.
    """
    text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    lines = text.splitlines()

    non_empty = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if not non_empty:
        return ""

    min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
    result = []
    for line in lines:
        stripped = line[min_indent:].rstrip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        result.append(stripped)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# ClonedFunction detection
# ---------------------------------------------------------------------------

def _detect_cloned_functions(
    body_data: list[_FuncBodyData],
    min_lines: int,
) -> list[SmellReport]:
    eligible = [f for f in body_data if f.body_line_count >= min_lines]

    groups: dict[str, list[_FuncBodyData]] = defaultdict(list)
    for func in eligible:
        groups[func.body_hash].append(func)

    reports: list[SmellReport] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for func in group:
            others = [f for f in group if f != func]
            other_strs = []
            for other in others:
                if other.file == func.file:
                    other_strs.append(f"'{other.name}' (line {other.start_line})")
                else:
                    other_strs.append(
                        f"'{other.name}' ({other.file}:{other.start_line})"
                    )
            reports.append(SmellReport(
                smell=_SMELL_CLONE,
                file=func.file,
                name=func.name,
                start_line=func.start_line,
                end_line=func.end_line,
                line_count=func.end_line - func.start_line + 1,
                clone_of=tuple((f.file, f.start_line) for f in others),
                message=(
                    f"Function '{func.name}' has an identical body to:"
                    f" {', '.join(other_strs)}."
                    " Consider extracting the shared logic."
                ),
            ))
    return reports


# ---------------------------------------------------------------------------
# DuplicateBlock detection
# ---------------------------------------------------------------------------

def _detect_duplicate_blocks(
    body_data: list[_FuncBodyData],
    min_block_stmts: int,
) -> list[SmellReport]:
    # window (tuple of stmt strings) → list of (func_data, window_start_index)
    window_map: dict[tuple, list[tuple[_FuncBodyData, int]]] = defaultdict(list)

    for func in body_data:
        n = len(func.stmts)
        for i in range(n - min_block_stmts + 1):
            window: tuple = func.stmts[i : i + min_block_stmts]
            window_map[window].append((func, i))

    reports: list[SmellReport] = []
    # Track (file, func_start_line) to emit at most one DuplicateBlock per function.
    seen_funcs: set[tuple[str, int]] = set()

    for window, occurrences in window_map.items():
        # Require occurrences in 2+ distinct functions
        func_ids = {(f.file, f.start_line) for f, _ in occurrences}
        if len(func_ids) < 2:
            continue

        for func, idx in occurrences:
            fid = (func.file, func.start_line)
            if fid in seen_funcs:
                continue
            seen_funcs.add(fid)

            block_start = func.stmt_ranges[idx][0]
            block_end = func.stmt_ranges[idx + min_block_stmts - 1][1]

            other_funcs = [f for f, _ in occurrences if (f.file, f.start_line) != fid]
            other_strs = []
            for other in other_funcs[:3]:
                if other.file == func.file:
                    other_strs.append(f"'{other.name}' (line {other.start_line})")
                else:
                    other_strs.append(
                        f"'{other.name}' ({other.file}:{other.start_line})"
                    )

            reports.append(SmellReport(
                smell=_SMELL_BLOCK,
                file=func.file,
                name=func.name,
                start_line=block_start,
                end_line=block_end,
                line_count=block_end - block_start + 1,
                clone_of=tuple((f.file, f.start_line) for f in other_funcs),
                message=(
                    f"Function '{func.name}' contains {min_block_stmts}+ duplicate"
                    f" statements also found in: {', '.join(other_strs)}."
                    " Consider extracting the shared logic."
                ),
            ))
    return reports
