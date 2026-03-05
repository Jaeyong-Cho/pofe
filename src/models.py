from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SmellReport:
    """A single detected code smell instance.

    Guarantees:
        - `file` is the path as given to `detect_smells`
        - `start_line` and `end_line` are 1-based
        - `line_count` equals `end_line - start_line + 1`
        - `name` is the function name for LongMethod, the class name for LargeClass

    Assumptions:
        - Created only by internal detectors; not intended for manual construction.
    """

    smell: str
    file: str
    name: str
    start_line: int
    end_line: int
    line_count: int
    message: str
    method_count: int | None = field(default=None)
    field_count: int | None = field(default=None)
