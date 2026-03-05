"""Tests for the Duplicate Code detector."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src import SmellReport, detect_smells
from src.duplicate_code import collect_body_data, detect, detect_from_collected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str, name: str = "sample.py") -> Path:
    f = tmp_path / name
    f.write_text(dedent(source))
    return f


# ---------------------------------------------------------------------------
# ClonedFunction — unit tests
# ---------------------------------------------------------------------------


class TestClonedFunction:
    def test_unique_bodies_not_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            def add(a, b):
                return a + b

            def subtract(a, b):
                return a - b
        """)
        assert detect(path) == []

    def test_trivial_function_under_min_lines_not_flagged(self, tmp_path):
        # Two identical 2-line bodies, default min_lines=3 → not flagged
        path = write_py(tmp_path, """\
            def f():
                x = 1
                return x

            def g():
                x = 1
                return x
        """)
        assert detect(path, min_lines=4) == []

    def test_identical_bodies_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            def compute_a(data):
                total = 0
                for item in data:
                    total += item
                return total

            def compute_b(data):
                total = 0
                for item in data:
                    total += item
                return total
        """)
        reports = detect(path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2
        names = {r.name for r in clones}
        assert names == {"compute_a", "compute_b"}

    def test_report_fields(self, tmp_path):
        path = write_py(tmp_path, """\
            def process_a(items):
                result = []
                for item in items:
                    result.append(item * 2)
                return result

            def process_b(items):
                result = []
                for item in items:
                    result.append(item * 2)
                return result
        """)
        reports = detect(path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2
        for r in clones:
            assert r.smell == "DuplicateCode.ClonedFunction"
            assert r.clone_of is not None
            assert len(r.clone_of) == 1
            assert "identical body" in r.message
            assert "shared logic" in r.message

    def test_three_clones_all_flagged(self, tmp_path):
        body = """\
            x = 1
            y = 2
            z = x + y
            return z
        """
        func = lambda name: f"def {name}(self):\n" + "\n".join(
            "    " + l for l in dedent(body).splitlines()
        ) + "\n"
        src = func("a") + "\n" + func("b") + "\n" + func("c")
        path = write_py(tmp_path, src)
        reports = detect(path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 3
        # each points to 2 others
        for r in clones:
            assert len(r.clone_of) == 2

    def test_comments_stripped_bodies_still_match(self, tmp_path):
        path = write_py(tmp_path, """\
            def first(data):
                # this processes data
                result = []
                for item in data:
                    result.append(item)
                return result

            def second(data):
                result = []
                for item in data:
                    result.append(item)
                return result
        """)
        reports = detect(path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2

    def test_different_indentation_still_matches(self, tmp_path):
        # Both bodies normalize to the same text despite extra indentation
        path = write_py(tmp_path, """\
            def a():
                x = 1
                y = 2
                z = 3
                return z

            def b():
                    x = 1
                    y = 2
                    z = 3
                    return z
        """)
        reports = detect(path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2

    def test_cross_file_clone_detected(self, tmp_path):
        body = dedent("""\
            def shared(data):
                result = []
                for item in data:
                    result.append(str(item))
                return result
        """)
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text(body)
        f2.write_text(body)
        data = collect_body_data(f1) + collect_body_data(f2)
        reports = detect_from_collected(data)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2
        files = {r.file for r in clones}
        assert str(f1) in files
        assert str(f2) in files

    def test_invalid_min_lines_raises(self, tmp_path):
        path = write_py(tmp_path, "def f(): pass\n")
        with pytest.raises(ValueError, match="min_lines must be >= 1"):
            detect(path, min_lines=0)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect(tmp_path / "missing.py")


# ---------------------------------------------------------------------------
# DuplicateBlock — unit tests
# ---------------------------------------------------------------------------


class TestDuplicateBlock:
    def test_no_shared_block_not_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            def f(a):
                x = a + 1
                y = x * 2
                return y

            def g(b):
                m = b - 1
                n = m / 3
                return n
        """)
        assert detect(path) == []

    def test_shared_block_at_threshold_flagged(self, tmp_path):
        # Exactly 3 shared consecutive statements
        path = write_py(tmp_path, """\
            def init_db(conn):
                conn.execute("BEGIN")
                conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")
                conn.execute("COMMIT")
                conn.close()

            def reset_db(conn):
                conn.execute("BEGIN")
                conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")
                conn.execute("COMMIT")
                conn.execute("VACUUM")
        """)
        reports = detect(path, min_block_stmts=3)
        blocks = [r for r in reports if r.smell == "DuplicateCode.DuplicateBlock"]
        assert len(blocks) == 2
        names = {r.name for r in blocks}
        assert names == {"init_db", "reset_db"}

    def test_below_threshold_not_flagged(self, tmp_path):
        # 2 shared statements but min_block_stmts=3
        path = write_py(tmp_path, """\
            def f(x):
                a = x + 1
                b = a * 2
                return b

            def g(x):
                a = x + 1
                b = a * 2
                return b * 3
        """)
        assert detect(path, min_block_stmts=3) == []

    def test_report_fields(self, tmp_path):
        path = write_py(tmp_path, """\
            def render_header(doc):
                doc.write("<html>")
                doc.write("<head>")
                doc.write("</head>")
                doc.write("<body>")

            def render_page(doc):
                doc.write("<html>")
                doc.write("<head>")
                doc.write("</head>")
                doc.write("<body>")
                doc.write("<p>content</p>")
        """)
        reports = detect(path, min_block_stmts=3)
        blocks = [r for r in reports if r.smell == "DuplicateCode.DuplicateBlock"]
        assert len(blocks) == 2
        for r in blocks:
            assert r.smell == "DuplicateCode.DuplicateBlock"
            assert r.clone_of is not None
            assert "duplicate" in r.message
            assert "shared logic" in r.message

    def test_block_in_one_function_only_not_flagged(self, tmp_path):
        # Same block appears twice in the SAME function but not in another
        path = write_py(tmp_path, """\
            def f(x):
                a = x + 1
                b = a * 2
                c = b - 3

            def g(x):
                m = x - 1
                n = m / 4
                o = n + 5
        """)
        assert detect(path, min_block_stmts=3) == []

    def test_invalid_min_block_stmts_raises(self, tmp_path):
        path = write_py(tmp_path, "def f(): pass\n")
        with pytest.raises(ValueError, match="min_block_stmts must be >= 2"):
            detect(path, min_block_stmts=1)

    def test_block_start_end_line_in_range(self, tmp_path):
        path = write_py(tmp_path, """\
            def setup(conn):
                conn.execute("BEGIN")
                conn.execute("SELECT 1")
                conn.execute("COMMIT")
                do_more()

            def teardown(conn):
                conn.execute("BEGIN")
                conn.execute("SELECT 1")
                conn.execute("COMMIT")
                cleanup()
        """)
        reports = detect(path, min_block_stmts=3)
        blocks = [r for r in reports if r.smell == "DuplicateCode.DuplicateBlock"]
        assert len(blocks) == 2
        for r in blocks:
            assert r.start_line <= r.end_line
            assert r.line_count == r.end_line - r.start_line + 1

    def test_cross_file_block_detected(self, tmp_path):
        common_block = (
            'conn.execute("BEGIN")\n'
            'conn.execute("SELECT 1")\n'
            'conn.execute("COMMIT")\n'
        )
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text(f"def func_a(conn):\n" + "".join(f"    {l}" for l in common_block.splitlines(keepends=True)) + "    return True\n")
        f2.write_text(f"def func_b(conn):\n" + "".join(f"    {l}" for l in common_block.splitlines(keepends=True)) + "    return False\n")
        data = collect_body_data(f1) + collect_body_data(f2)
        reports = detect_from_collected(data, min_block_stmts=3)
        blocks = [r for r in reports if r.smell == "DuplicateCode.DuplicateBlock"]
        assert len(blocks) == 2


# ---------------------------------------------------------------------------
# Integration — detect_smells public API
# ---------------------------------------------------------------------------


class TestDetectSmellsDuplicateCode:
    def test_cloned_function_via_public_api(self, tmp_path):
        src = dedent("""\
            def compute_a(data):
                total = 0
                for item in data:
                    total += item
                return total

            def compute_b(data):
                total = 0
                for item in data:
                    total += item
                return total
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert len(clones) == 2

    def test_duplicate_block_via_public_api(self, tmp_path):
        src = dedent("""\
            def init(conn):
                conn.execute("BEGIN")
                conn.execute("CREATE TABLE t (id INT)")
                conn.execute("COMMIT")

            def reset(conn):
                conn.execute("BEGIN")
                conn.execute("CREATE TABLE t (id INT)")
                conn.execute("COMMIT")
                conn.execute("DELETE FROM t")
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path, duplicate_code_min_block_stmts=3)
        blocks = [r for r in reports if r.smell == "DuplicateCode.DuplicateBlock"]
        assert len(blocks) == 2

    def test_min_lines_threshold_via_public_api(self, tmp_path):
        # Identical 3-line bodies; min_lines=4 → not flagged
        src = dedent("""\
            def f():
                x = 1
                y = 2
                return y

            def g():
                x = 1
                y = 2
                return y
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path, duplicate_code_min_lines=4)
        clones = [r for r in reports if r.smell == "DuplicateCode.ClonedFunction"]
        assert clones == []

    def test_all_detectors_run_together(self, tmp_path):
        src = dedent("""\
            def process_x(data):
                result = []
                for item in data:
                    result.append(item * 2)
                return result

            def process_y(data):
                result = []
                for item in data:
                    result.append(item * 2)
                return result
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path)
        smells = {r.smell for r in reports}
        assert "DuplicateCode.ClonedFunction" in smells
