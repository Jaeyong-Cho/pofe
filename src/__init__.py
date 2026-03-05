"""Code smell detector for Python source files.

Public API:

    detect_smells(path, *, long_method_threshold=20,
                  large_class_line_threshold=200,
                  large_class_method_threshold=20,
                  large_class_field_threshold=10,
                  type_code_threshold=3,
                  primitive_param_threshold=5) -> list[SmellReport]

        Scan a Python file (or all .py files under a directory) for code smells.
        Returns one SmellReport per detected instance, sorted by file and line.

    SmellReport
        Frozen dataclass with fields:
            smell           : str       - smell name ("LongMethod", "LargeClass",
                                          "PrimitiveObsession.TypeCode",
                                          "PrimitiveObsession.PrimitiveParameterCluster")
            file            : str       - source file path
            name            : str       - function, class, or scope name
            start_line      : int       - 1-based start line
            end_line        : int       - 1-based end line
            line_count      : int       - physical lines (end_line - start_line + 1)
            message         : str       - human-readable description
            method_count    : int|None  - number of methods  (LargeClass only)
            field_count     : int|None  - number of fields   (LargeClass only)
            primitive_count : int|None  - number of primitives (PrimitiveObsession only)
"""

from __future__ import annotations

from pathlib import Path

from .large_class import detect as _detect_large_class
from .long_method import detect as _detect_long_method
from .models import SmellReport
from .primitive_obsession import detect as _detect_primitive_obsession

__all__ = ["SmellReport", "detect_smells"]


def detect_smells(
    path: str | Path,
    *,
    long_method_threshold: int = 20,
    large_class_line_threshold: int = 200,
    large_class_method_threshold: int = 20,
    large_class_field_threshold: int = 10,
    type_code_threshold: int = 3,
    primitive_param_threshold: int = 5,
) -> list[SmellReport]:
    """Detect code smells in a Python file or directory.

    Args:
        path: A Python source file or a directory. Directories are scanned
              recursively for all `*.py` files.
        long_method_threshold:       Flag functions with more physical lines.
        large_class_line_threshold:  Flag classes with more physical lines.
        large_class_method_threshold: Flag classes with more methods.
        large_class_field_threshold: Flag classes with more fields.
        type_code_threshold:         Flag scopes with this many+ ALL_CAPS primitive constants.
        primitive_param_threshold:   Flag functions with this many+ primitive-typed params.

    Returns:
        A list of SmellReport sorted by (file, start_line).
        Empty list when no smells are found.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If any threshold is less than 1.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    files = list(target.rglob("*.py")) if target.is_dir() else [target]

    reports: list[SmellReport] = []
    for file in files:
        reports.extend(_detect_long_method(file, threshold=long_method_threshold))
        reports.extend(
            _detect_large_class(
                file,
                line_threshold=large_class_line_threshold,
                method_threshold=large_class_method_threshold,
                field_threshold=large_class_field_threshold,
            )
        )
        reports.extend(
            _detect_primitive_obsession(
                file,
                type_code_threshold=type_code_threshold,
                primitive_param_threshold=primitive_param_threshold,
            )
        )

    reports.sort(key=lambda r: (r.file, r.start_line))
    return reports
