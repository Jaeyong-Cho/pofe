"""Tests for the Large Class detector."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import SmellReport, detect_smells
from src.large_class import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(source)
    return f


def make_class(
    name: str = "MyClass",
    methods: int = 0,
    instance_fields: int = 0,
    extra_lines: int = 0,
) -> str:
    """Build a Python class source string with the given number of methods and fields."""
    lines = [f"class {name}:"]

    # class body: one __init__ with `self.x0 = 0 ... self.xN = N`
    if instance_fields > 0:
        lines.append("    def __init__(self):")
        for i in range(instance_fields):
            lines.append(f"        self.field{i} = {i}")

    for i in range(methods):
        lines.append(f"    def method{i}(self):")
        lines.append("        pass")

    # extra real assignment statements to inflate line count
    lines.extend([f"    _pad{i} = None" for i in range(extra_lines)])

    if len(lines) == 1:
        lines.append("    pass")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# large_class.detect — unit tests
# ---------------------------------------------------------------------------


class TestLargeClassDetect:
    def test_small_class_not_flagged(self, tmp_path):
        src = make_class(methods=3, instance_fields=3)
        path = write_py(tmp_path, src)
        assert detect(path, line_threshold=200, method_threshold=20, field_threshold=10) == []

    def test_class_at_method_threshold_not_flagged(self, tmp_path):
        # Exactly threshold — should NOT be flagged (must exceed, not equal)
        src = make_class(methods=20)
        path = write_py(tmp_path, src)
        assert detect(path, method_threshold=20) == []

    def test_class_exceeding_method_threshold_flagged(self, tmp_path):
        src = make_class(methods=21)
        path = write_py(tmp_path, src)
        reports = detect(path, method_threshold=20)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "LargeClass"
        assert r.name == "MyClass"
        assert r.method_count == 21
        assert "21 methods" in r.message

    def test_class_exceeding_field_threshold_flagged(self, tmp_path):
        src = make_class(instance_fields=11)
        path = write_py(tmp_path, src)
        reports = detect(path, field_threshold=10)
        assert len(reports) == 1
        r = reports[0]
        assert r.field_count == 11
        assert "11 fields" in r.message

    def test_class_exceeding_line_threshold_flagged(self, tmp_path):
        src = make_class(extra_lines=201)
        path = write_py(tmp_path, src)
        reports = detect(path, line_threshold=200)
        assert len(reports) == 1
        assert reports[0].line_count > 200

    def test_multiple_criteria_all_reported_in_message(self, tmp_path):
        src = make_class(methods=21, instance_fields=11)
        path = write_py(tmp_path, src)
        reports = detect(path, method_threshold=20, field_threshold=10)
        assert len(reports) == 1
        msg = reports[0].message
        assert "methods" in msg
        assert "fields" in msg

    def test_multiple_classes_only_large_ones_flagged(self, tmp_path):
        small = make_class("Small", methods=2)
        large = make_class("Big", methods=21)
        path = write_py(tmp_path, small + "\n" + large)
        reports = detect(path, method_threshold=20)
        assert len(reports) == 1
        assert reports[0].name == "Big"

    def test_class_level_annotations_count_as_fields(self, tmp_path):
        src = (
            "class Cfg:\n"
            "    x: int = 1\n"
            "    y: str = 'a'\n"
            "    z: float = 3.0\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, field_threshold=2)
        assert len(reports) == 1
        assert reports[0].field_count >= 3

    def test_decorated_methods_counted(self, tmp_path):
        methods = "\n".join(
            f"    @staticmethod\n    def method{i}():\n        pass"
            for i in range(21)
        )
        src = f"class Decorated:\n{methods}\n"
        path = write_py(tmp_path, src)
        reports = detect(path, method_threshold=20)
        assert len(reports) == 1
        assert reports[0].method_count == 21

    def test_nested_functions_not_counted_as_methods(self, tmp_path):
        # inner() is a nested function inside a method — not a class method.
        src = (
            "class MyClass:\n"
            "    def outer(self):\n"
            "        def inner(): pass\n"
            "        return inner\n"
            "    def another(self): pass\n"  # 2 real methods
        )
        path = write_py(tmp_path, src)
        # Exceeds threshold of 1 → gets reported.
        reports = detect(path, method_threshold=1)
        assert len(reports) == 1
        # inner() must not be counted as a method.
        assert reports[0].method_count == 2

    def test_report_fields_are_correct(self, tmp_path):
        src = make_class("Target", methods=21)
        path = write_py(tmp_path, src)
        r = detect(path, method_threshold=20)[0]
        assert r.file == str(path)
        assert r.start_line >= 1
        assert r.end_line == r.start_line + r.line_count - 1
        assert "Target" in r.message

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "class A: pass\n")
        with pytest.raises(ValueError):
            detect(path, line_threshold=0)
        with pytest.raises(ValueError):
            detect(path, method_threshold=0)
        with pytest.raises(ValueError):
            detect(path, field_threshold=0)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            detect("/nonexistent/file.py")

    def test_empty_class_not_flagged(self, tmp_path):
        path = write_py(tmp_path, "class Empty: pass\n")
        assert detect(path) == []

    def test_self_attrs_in_non_init_methods_count_as_fields(self, tmp_path):
        src = (
            "class MyClass:\n"
            "    def setup(self):\n"
            + "".join(f"        self.f{i} = {i}\n" for i in range(11))
        )
        path = write_py(tmp_path, src)
        reports = detect(path, field_threshold=10)
        assert len(reports) == 1
        assert reports[0].field_count >= 11

    def test_self_attrs_in_nested_function_not_counted(self, tmp_path):
        # self.hidden is assigned only inside a nested function; it must not
        # be counted as a field of MyClass.
        # Add enough outer methods to trigger reporting via method_threshold=1.
        src = (
            "class MyClass:\n"
            "    def method(self):\n"
            "        def nested():\n"
            "            self.hidden = 1\n"
            "        nested()\n"
            "    def another(self): pass\n"  # 2 methods → exceeds threshold 1
        )
        path = write_py(tmp_path, src)
        reports = detect(path, method_threshold=1)
        assert len(reports) == 1
        assert reports[0].field_count == 0


# ---------------------------------------------------------------------------
# detect_smells (public API) — integration tests for LargeClass
# ---------------------------------------------------------------------------


class TestDetectSmellsLargeClass:
    def test_large_class_in_single_file(self, tmp_path):
        src = make_class(methods=21)
        f = tmp_path / "big.py"
        f.write_text(src)
        reports = detect_smells(f, large_class_method_threshold=20)
        assert any(r.smell == "LargeClass" for r in reports)

    def test_custom_thresholds_respected(self, tmp_path):
        src = make_class(methods=5, instance_fields=5)
        f = tmp_path / "medium.py"
        f.write_text(src)
        assert detect_smells(f, large_class_method_threshold=20, large_class_field_threshold=10) == []
        reports = detect_smells(f, large_class_method_threshold=4)
        assert any(r.smell == "LargeClass" for r in reports)

    def test_both_detectors_run_together(self, tmp_path):
        long_fn_body = "\n".join(f"    x{i} = {i}" for i in range(25))
        src = (
            f"def long_fn():\n{long_fn_body}\n    return 0\n\n"
            + make_class(methods=21)
        )
        f = tmp_path / "both.py"
        f.write_text(src)
        reports = detect_smells(f, long_method_threshold=20, large_class_method_threshold=20)
        smells = {r.smell for r in reports}
        assert "LongMethod" in smells
        assert "LargeClass" in smells
