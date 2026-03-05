from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SmellReport:
    """A single detected code smell instance.

    Guarantees:
        - `file` is the path as given to `detect_smells`
        - `start_line` and `end_line` are 1-based
        - `line_count` equals `end_line - start_line + 1`
        - `name` is the function/class/scope name depending on the detector

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
    primitive_count: int | None = field(default=None)
    clump: tuple | None = field(default=None)
    branch_count: int | None = field(default=None)
    temp_fields: tuple | None = field(default=None)
