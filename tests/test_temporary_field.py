"""Tests for the Temporary Field detector."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src import SmellReport, detect_smells
from src.temporary_field import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(dedent(source))
    return f


# ---------------------------------------------------------------------------
# Pure temp (no __init__ write) — unit tests
# ---------------------------------------------------------------------------


class TestPureTemp:
    def test_regular_field_not_flagged(self, tmp_path):
        # Field set and read in __init__, and read elsewhere → regular field
        path = write_py(tmp_path, """\
            class Greeter:
                def __init__(self, name):
                    self.name = name

                def greet(self):
                    return f"Hello, {self.name}"
        """)
        assert detect(path) == []

    def test_field_set_and_read_same_method_not_flagged(self, tmp_path):
        # Written and read only in compute() → no cross-method dependency
        path = write_py(tmp_path, """\
            class Processor:
                def compute(self, data):
                    self.result = sum(data)
                    return self.result
        """)
        assert detect(path) == []

    def test_pure_temp_field_flagged(self, tmp_path):
        # self.result set in compute(), read in render() → temp field
        path = write_py(tmp_path, """\
            class Report:
                def compute(self, data):
                    self.result = sum(data)

                def render(self):
                    return str(self.result)
        """)
        reports = detect(path)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "TemporaryField"
        assert r.name == "Report"
        assert r.temp_fields == ("result",)
        assert "'result'" in r.message
        assert "Method Object" in r.message

    def test_report_fields(self, tmp_path):
        path = write_py(tmp_path, """\
            class Encoder:
                def prepare(self, data):
                    self.buf = data.encode()

                def flush(self):
                    return self.buf
        """)
        reports = detect(path)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "TemporaryField"
        assert r.file == str(tmp_path / "sample.py")
        assert r.start_line >= 1
        assert r.end_line >= r.start_line
        assert r.line_count == r.end_line - r.start_line + 1
        assert r.temp_fields == ("buf",)

    def test_multiple_temp_fields_flagged_together(self, tmp_path):
        # Both self.memo and self.cache set only in preprocess()
        path = write_py(tmp_path, """\
            class Transformer:
                def preprocess(self, data):
                    self.memo = {}
                    self.cache = []

                def transform(self, key):
                    return self.memo.get(key)

                def validate(self):
                    return len(self.cache) > 0
        """)
        reports = detect(path)
        assert len(reports) == 1
        r = reports[0]
        assert set(r.temp_fields) == {"memo", "cache"}
        assert "2 temporary fields" in r.message

    def test_threshold_respected(self, tmp_path):
        # 1 temp field, threshold=2 → not flagged
        path = write_py(tmp_path, """\
            class Report:
                def compute(self, data):
                    self.result = sum(data)

                def render(self):
                    return str(self.result)
        """)
        assert detect(path, threshold=2) == []

    def test_field_written_in_two_methods_not_flagged(self, tmp_path):
        # Written in both build() and rebuild() → more than 1 non-init writer
        path = write_py(tmp_path, """\
            class Cache:
                def build(self, data):
                    self.store = data

                def rebuild(self, data):
                    self.store = data

                def lookup(self, key):
                    return self.store.get(key)
        """)
        assert detect(path) == []

    def test_init_sets_real_value_not_flagged(self, tmp_path):
        # __init__ writes self.data (to a real value), so it's NOT a temp field
        path = write_py(tmp_path, """\
            class Processor:
                def __init__(self, data):
                    self.data = data

                def process(self):
                    self.data = transform(self.data)

                def report(self):
                    return self.data
        """)
        assert detect(path) == []


# ---------------------------------------------------------------------------
# Init-None temp pattern — unit tests
# ---------------------------------------------------------------------------


class TestInitNoneTemp:
    def test_init_none_then_set_in_one_method_flagged(self, tmp_path):
        # self.result = None in __init__; real value in compute(); read in render()
        path = write_py(tmp_path, """\
            class Report:
                def __init__(self):
                    self.result = None

                def compute(self, data):
                    self.result = sum(data)

                def render(self):
                    return str(self.result)
        """)
        reports = detect(path)
        assert len(reports) == 1
        assert reports[0].temp_fields == ("result",)

    def test_init_none_only_read_in_setter_not_flagged(self, tmp_path):
        # __init__ sets to None, compute() sets real value, but no other method reads
        path = write_py(tmp_path, """\
            class Obj:
                def __init__(self):
                    self.val = None

                def set_val(self, v):
                    self.val = v
        """)
        assert detect(path) == []

    def test_init_real_value_overwrite_not_flagged(self, tmp_path):
        # __init__ sets self.x to a real (non-None) value → not a temp field
        path = write_py(tmp_path, """\
            class Counter:
                def __init__(self):
                    self.count = 0

                def increment(self):
                    self.count += 1

                def value(self):
                    return self.count
        """)
        assert detect(path) == []

    def test_multiple_init_none_fields_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            class Solver:
                def __init__(self):
                    self.path = None
                    self.cost = None

                def solve(self, graph):
                    self.path = []
                    self.cost = 0

                def report(self):
                    return self.path, self.cost
        """)
        reports = detect(path)
        assert len(reports) == 1
        assert set(reports[0].temp_fields) == {"path", "cost"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_class_not_flagged(self, tmp_path):
        path = write_py(tmp_path, "class Empty: pass\n")
        assert detect(path) == []

    def test_class_with_only_init_not_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            class Config:
                def __init__(self, x):
                    self.x = x
        """)
        assert detect(path) == []

    def test_nested_function_writes_not_attributed_to_outer_method(self, tmp_path):
        # self.x written inside a nested function in compute() should NOT
        # make self.x a write of compute() — nested functions have their own scope
        path = write_py(tmp_path, """\
            class Worker:
                def compute(self):
                    def inner():
                        self.result = 42  # written inside nested function
                    inner()

                def display(self):
                    return self.result
        """)
        # result is NOT written in compute() (it's in inner()) → not flagged
        assert detect(path) == []

    def test_augmented_assignment_counts_as_write(self, tmp_path):
        # self.total += x is a write of compute(); read in report()
        path = write_py(tmp_path, """\
            class Accumulator:
                def accumulate(self, x):
                    self.total += x

                def report(self):
                    return self.total
        """)
        reports = detect(path)
        assert len(reports) == 1
        assert reports[0].temp_fields == ("total",)

    def test_self_x_in_expression_counts_as_read(self, tmp_path):
        # compute() writes self.buf; render() uses self.buf in expression
        path = write_py(tmp_path, """\
            class Encoder:
                def load(self, data):
                    self.buf = data

                def serialize(self):
                    return list(self.buf)
        """)
        reports = detect(path)
        assert len(reports) == 1

    def test_multiple_classes_each_analyzed_independently(self, tmp_path):
        path = write_py(tmp_path, """\
            class A:
                def setup(self, data):
                    self.x = data

                def run(self):
                    return self.x

            class B:
                def __init__(self, y):
                    self.y = y

                def use(self):
                    return self.y
        """)
        reports = detect(path)
        assert len(reports) == 1
        assert reports[0].name == "A"

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect(tmp_path / "missing.py")

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "class X: pass\n")
        with pytest.raises(ValueError, match="threshold must be >= 1"):
            detect(path, threshold=0)

    def test_async_method_detected(self, tmp_path):
        path = write_py(tmp_path, """\
            class Fetcher:
                async def fetch(self, url):
                    self.data = await download(url)

                def process(self):
                    return parse(self.data)
        """)
        reports = detect(path)
        assert len(reports) == 1
        assert reports[0].temp_fields == ("data",)

    def test_decorated_method_detected(self, tmp_path):
        path = write_py(tmp_path, """\
            class Service:
                @staticmethod
                def prepare(self, payload):
                    self.pending = payload

                def dispatch(self):
                    return self.pending
        """)
        reports = detect(path)
        assert len(reports) == 1


# ---------------------------------------------------------------------------
# Integration — detect_smells public API
# ---------------------------------------------------------------------------


class TestDetectSmellsTemporaryField:
    def test_temp_field_detected_via_public_api(self, tmp_path):
        src = dedent("""\
            class Report:
                def compute(self, data):
                    self.result = sum(data)

                def render(self):
                    return str(self.result)
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path)
        tf = [r for r in reports if r.smell == "TemporaryField"]
        assert len(tf) == 1
        assert tf[0].name == "Report"

    def test_threshold_respected_via_public_api(self, tmp_path):
        src = dedent("""\
            class Report:
                def compute(self, data):
                    self.result = sum(data)

                def render(self):
                    return str(self.result)
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path, temporary_field_threshold=2)
        tf = [r for r in reports if r.smell == "TemporaryField"]
        assert tf == []

    def test_all_detectors_run_together(self, tmp_path):
        src = dedent("""\
            class Analyzer:
                def analyze(self, items):
                    self.summary = [str(i) for i in items]

                def display(self):
                    print(self.summary)
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path)
        smells = {r.smell for r in reports}
        assert "TemporaryField" in smells
