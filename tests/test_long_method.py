"""Tests for the Long Method detector."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src import SmellReport, detect_smells
from src.long_method import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str) -> Path:
    """Write `source` to a temp .py file and return its path."""
    f = tmp_path / "sample.py"
    f.write_text(textwrap.dedent(source))
    return f


# ---------------------------------------------------------------------------
# _long_method.detect — unit tests
# ---------------------------------------------------------------------------


class TestLongMethodDetect:
    def test_short_function_not_flagged(self, tmp_path):
        src = """\
            def short():
                x = 1
                return x
        """
        path = write_py(tmp_path, src)
        assert detect(path, threshold=20) == []

    def test_function_at_threshold_not_flagged(self, tmp_path):
        # Exactly threshold lines — should NOT be flagged (must exceed, not equal)
        body = "\n".join(f"    x{i} = {i}" for i in range(18))  # 18 body lines
        src = f"def at_limit():\n{body}\n    return 0\n"  # 20 lines total
        path = write_py(tmp_path, src)
        assert detect(path, threshold=20) == []

    def test_function_exceeding_threshold_flagged(self, tmp_path):
        body = "\n".join(f"    x{i} = {i}" for i in range(20))  # 20 body lines
        src = f"def too_long():\n{body}\n    return 0\n"  # 22 lines total
        path = write_py(tmp_path, src)
        reports = detect(path, threshold=20)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "LongMethod"
        assert r.name == "too_long"
        assert r.line_count == 22

    def test_multiple_functions_only_long_ones_flagged(self, tmp_path):
        short_fn = "def short():\n    return 1\n\n"
        long_body = "\n".join(f"    x{i} = {i}" for i in range(25))
        long_fn = f"def long_fn():\n{long_body}\n    return 0\n"
        path = write_py(tmp_path, short_fn + long_fn)

        reports = detect(path, threshold=20)
        assert len(reports) == 1
        assert reports[0].name == "long_fn"

    def test_method_inside_class_flagged(self, tmp_path):
        body = "\n".join(f"        x{i} = {i}" for i in range(25))
        src = f"class Foo:\n    def big_method(self):\n{body}\n        return 0\n"
        path = write_py(tmp_path, src)
        reports = detect(path, threshold=20)
        assert len(reports) == 1
        assert reports[0].name == "big_method"

    def test_nested_function_flagged_independently(self, tmp_path):
        inner_body = "\n".join(f"        x{i} = {i}" for i in range(25))
        src = (
            "def outer():\n"
            f"    def inner():\n"
            f"{inner_body}\n"
            "        return 0\n"
            "    return inner\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, threshold=20)
        names = {r.name for r in reports}
        assert "inner" in names

    def test_report_fields_are_correct(self, tmp_path):
        body = "\n".join(f"    x{i} = {i}" for i in range(20))
        src = f"def my_func():\n{body}\n    return 0\n"
        path = write_py(tmp_path, src)
        r = detect(path, threshold=20)[0]
        assert r.file == str(path)
        assert r.start_line == 1
        assert r.end_line == r.start_line + r.line_count - 1
        assert "my_func" in r.message
        assert "threshold: 20" in r.message

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "def f(): pass\n")
        with pytest.raises(ValueError):
            detect(path, threshold=0)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            detect("/nonexistent/file.py")

    def test_blank_lines_included_in_count(self, tmp_path):
        # Blank lines inside the function body count toward physical LOC
        lines = ["def spaced():"]
        for i in range(10):
            lines.append(f"    x{i} = {i}")
            lines.append("")  # blank line after each statement
        lines.append("    return 0")
        src = "\n".join(lines) + "\n"
        path = write_py(tmp_path, src)
        reports = detect(path, threshold=20)
        assert len(reports) == 1
        assert reports[0].line_count > 20


# ---------------------------------------------------------------------------
# detect_smells (public API) — integration tests
# ---------------------------------------------------------------------------


class TestDetectSmells:
    def test_single_file(self, tmp_path):
        body = "\n".join(f"    x{i} = {i}" for i in range(25))
        src = f"def big():\n{body}\n    return 0\n"
        f = tmp_path / "big.py"
        f.write_text(src)
        reports = detect_smells(f)
        assert len(reports) == 1
        assert isinstance(reports[0], SmellReport)

    def test_directory_scanned_recursively(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        body = "\n".join(f"    x{i} = {i}" for i in range(25))
        (tmp_path / "a.py").write_text(f"def big():\n{body}\n    return 0\n")
        (sub / "b.py").write_text(f"def big2():\n{body}\n    return 0\n")
        (tmp_path / "c.py").write_text("def small(): pass\n")

        reports = detect_smells(tmp_path)
        assert len(reports) == 2

    def test_results_sorted_by_file_then_line(self, tmp_path):
        body = "\n".join(f"    x{i} = {i}" for i in range(25))
        fn = f"def big():\n{body}\n    return 0\n"
        (tmp_path / "b.py").write_text(fn)
        (tmp_path / "a.py").write_text(fn)

        reports = detect_smells(tmp_path)
        assert reports[0].file <= reports[1].file

    def test_custom_threshold(self, tmp_path):
        body = "\n".join(f"    x{i} = {i}" for i in range(8))
        fn = f"def medium():\n{body}\n    return 0\n"  # 10 lines
        f = tmp_path / "m.py"
        f.write_text(fn)

        assert detect_smells(f, long_method_threshold=20) == []
        assert len(detect_smells(f, long_method_threshold=5)) == 1

    def test_path_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            detect_smells("/nonexistent/path")

    def test_empty_file_no_smells(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert detect_smells(f) == []
