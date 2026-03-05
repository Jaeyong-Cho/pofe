"""CLI entry point.

Usage:
    python -m src <path> [options]
    python src/main.py <path> [options]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python src/main.py` (no parent package context).
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src import detect_smells
else:
    from . import detect_smells


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="smell_detector",
        description="Detect code smells in Python source files.",
    )
    parser.add_argument(
        "path",
        help="Python file or directory to scan.",
    )
    parser.add_argument(
        "--long-method-threshold",
        type=int,
        default=20,
        metavar="N",
        help="Flag functions longer than N lines as LongMethod (default: 20).",
    )
    parser.add_argument(
        "--large-class-line-threshold",
        type=int,
        default=200,
        metavar="N",
        help="Flag classes with more than N physical lines as LargeClass (default: 200).",
    )
    parser.add_argument(
        "--large-class-method-threshold",
        type=int,
        default=20,
        metavar="N",
        help="Flag classes with more than N methods as LargeClass (default: 20).",
    )
    parser.add_argument(
        "--large-class-field-threshold",
        type=int,
        default=10,
        metavar="N",
        help="Flag classes with more than N fields as LargeClass (default: 10).",
    )
    parser.add_argument(
        "--type-code-threshold",
        type=int,
        default=3,
        metavar="N",
        help="Flag scopes with N+ ALL_CAPS primitive constants as PrimitiveObsession (default: 3).",
    )
    parser.add_argument(
        "--primitive-param-threshold",
        type=int,
        default=5,
        metavar="N",
        help="Flag functions with N+ primitive-typed parameters as PrimitiveObsession (default: 5).",
    )
    parser.add_argument(
        "--data-clump-size",
        type=int,
        default=3,
        metavar="N",
        help="Flag functions/classes sharing N+ names as DataClump (default: 3).",
    )
    parser.add_argument(
        "--if-else-chain-threshold",
        type=int,
        default=3,
        metavar="N",
        help="Flag if/elif chains with N+ total branches as SwitchStatement (default: 3).",
    )
    parser.add_argument(
        "--match-case-threshold",
        type=int,
        default=3,
        metavar="N",
        help="Flag match statements with N+ cases as SwitchStatement (default: 3).",
    )
    parser.add_argument(
        "--temporary-field-threshold",
        type=int,
        default=1,
        metavar="N",
        help="Flag classes with N+ temporary fields as TemporaryField (default: 1).",
    )
    parser.add_argument(
        "--duplicate-code-min-lines",
        type=int,
        default=3,
        metavar="N",
        help="Minimum effective lines for ClonedFunction detection (default: 3).",
    )
    parser.add_argument(
        "--duplicate-code-min-block-stmts",
        type=int,
        default=3,
        metavar="N",
        help="Minimum consecutive statements for DuplicateBlock detection (default: 3).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args()

    try:
        reports = detect_smells(
            args.path,
            long_method_threshold=args.long_method_threshold,
            large_class_line_threshold=args.large_class_line_threshold,
            large_class_method_threshold=args.large_class_method_threshold,
            large_class_field_threshold=args.large_class_field_threshold,
            type_code_threshold=args.type_code_threshold,
            primitive_param_threshold=args.primitive_param_threshold,
            data_clump_size=args.data_clump_size,
            if_else_chain_threshold=args.if_else_chain_threshold,
            match_case_threshold=args.match_case_threshold,
            temporary_field_threshold=args.temporary_field_threshold,
            duplicate_code_min_lines=args.duplicate_code_min_lines,
            duplicate_code_min_block_stmts=args.duplicate_code_min_block_stmts,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        _print_json(reports)
    else:
        _print_text(reports)

    sys.exit(1 if reports else 0)


def _print_text(reports) -> None:
    if not reports:
        print("No code smells found.")
        return

    for r in reports:
        print(f"{r.file}:{r.start_line}: [{r.smell}] {r.message}")

    print(f"\n{len(reports)} smell(s) found.")


def _print_json(reports) -> None:
    import dataclasses
    import json

    print(json.dumps([dataclasses.asdict(r) for r in reports], indent=2))


if __name__ == "__main__":
    main()
