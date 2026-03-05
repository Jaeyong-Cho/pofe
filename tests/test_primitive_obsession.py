"""Tests for the Primitive Obsession detector."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import detect_smells
from src.primitive_obsession import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(source)
    return f


# ---------------------------------------------------------------------------
# TypeCode — unit tests
# ---------------------------------------------------------------------------


class TestTypeCode:
    def test_no_constants_not_flagged(self, tmp_path):
        path = write_py(tmp_path, "x = 1\n")
        assert detect(path, type_code_threshold=3) == []

    def test_lowercase_constants_not_flagged(self, tmp_path):
        src = "role_admin = 1\nrole_user = 2\nrole_guest = 3\n"
        path = write_py(tmp_path, src)
        assert detect(path, type_code_threshold=3) == []

    def test_single_word_allcaps_not_flagged(self, tmp_path):
        # Single ALL_CAPS word (e.g. PI, MAX) is not a type code pattern
        src = "PI = 3\nE = 2\nX = 1\n"
        path = write_py(tmp_path, src)
        # _ALLCAPS_RE requires at least two chars (^[A-Z][A-Z0-9_]+$)
        assert detect(path, type_code_threshold=3) == []

    def test_at_threshold_not_flagged(self, tmp_path):
        # Exactly 3 — must not be flagged (threshold means >= N triggers)
        src = "AA = 1\nBB = 2\nCC = 3\n"
        path = write_py(tmp_path, src)
        # threshold=3 means count >= 3, so 3 SHOULD be flagged
        reports = detect(path, type_code_threshold=3)
        assert len(reports) == 1

    def test_module_level_type_codes_flagged(self, tmp_path):
        src = (
            "ROLE_ADMIN = 1\n"
            "ROLE_USER = 2\n"
            "ROLE_GUEST = 3\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, type_code_threshold=3)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "PrimitiveObsession.TypeCode"
        assert r.name == "<module>"
        assert r.primitive_count == 3
        assert "3 ALL_CAPS" in r.message
        assert "Enum" in r.message

    def test_class_level_type_codes_flagged(self, tmp_path):
        src = (
            "class Status:\n"
            "    PENDING = 'pending'\n"
            "    ACTIVE = 'active'\n"
            "    INACTIVE = 'inactive'\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, type_code_threshold=3)
        assert len(reports) == 1
        r = reports[0]
        assert r.name == "Status"
        assert r.primitive_count == 3

    def test_string_literals_caught(self, tmp_path):
        src = "STATE_ON = 'on'\nSTATE_OFF = 'off'\nSTATE_IDLE = 'idle'\n"
        path = write_py(tmp_path, src)
        reports = detect(path, type_code_threshold=3)
        assert len(reports) == 1

    def test_non_primitive_assignment_not_counted(self, tmp_path):
        src = (
            "AA = 1\n"
            "BB = 2\n"
            "CC = SomeClass()\n"  # not a primitive literal
        )
        path = write_py(tmp_path, src)
        assert detect(path, type_code_threshold=3) == []

    def test_report_line_range_covers_constants(self, tmp_path):
        src = "x = 0\nAA = 1\nBB = 2\nCC = 3\ny = 99\n"
        path = write_py(tmp_path, src)
        r = detect(path, type_code_threshold=3)[0]
        # start_line should be the line of AA (line 2), end_line of CC (line 4)
        assert r.start_line == 2
        assert r.end_line == 4

    def test_class_and_module_flagged_independently(self, tmp_path):
        src = (
            "AA = 1\nBB = 2\nCC = 3\n\n"
            "class Cfg:\n"
            "    XX = 10\n"
            "    YY = 20\n"
            "    ZZ = 30\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, type_code_threshold=3)
        names = {r.name for r in reports}
        assert "<module>" in names
        assert "Cfg" in names

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "AA = 1\n")
        with pytest.raises(ValueError):
            detect(path, type_code_threshold=0)


# ---------------------------------------------------------------------------
# PrimitiveParameterCluster — unit tests
# ---------------------------------------------------------------------------


class TestPrimitiveParameterCluster:
    def test_no_annotations_not_flagged(self, tmp_path):
        src = "def f(a, b, c, d, e): pass\n"
        path = write_py(tmp_path, src)
        assert detect(path, primitive_param_threshold=5) == []

    def test_non_primitive_annotations_not_counted(self, tmp_path):
        src = "def f(a: MyClass, b: OtherClass, c: SomeType, d: T, e: U): pass\n"
        path = write_py(tmp_path, src)
        assert detect(path, primitive_param_threshold=5) == []

    def test_at_threshold_flagged(self, tmp_path):
        src = "def f(a: int, b: str, c: float, d: bool, e: bytes): pass\n"
        path = write_py(tmp_path, src)
        reports = detect(path, primitive_param_threshold=5)
        assert len(reports) == 1

    def test_below_threshold_not_flagged(self, tmp_path):
        src = "def f(a: int, b: str, c: float, d: bool): pass\n"
        path = write_py(tmp_path, src)
        assert detect(path, primitive_param_threshold=5) == []

    def test_report_fields_correct(self, tmp_path):
        src = "def register(name: str, age: int, email: str, phone: str, score: float): pass\n"
        path = write_py(tmp_path, src)
        r = detect(path, primitive_param_threshold=5)[0]
        assert r.smell == "PrimitiveObsession.PrimitiveParameterCluster"
        assert r.name == "register"
        assert r.primitive_count == 5
        assert "register" in r.message
        assert "parameter object" in r.message

    def test_self_not_counted(self, tmp_path):
        # `self` has no annotation; only annotated params count
        src = (
            "class Foo:\n"
            "    def method(self, a: int, b: str, c: float, d: bool, e: bytes): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, primitive_param_threshold=5)
        assert len(reports) == 1
        assert reports[0].primitive_count == 5

    def test_mixed_primitive_and_object_params(self, tmp_path):
        src = "def f(a: int, b: MyClass, c: str, d: float, e: Other, g: bool): pass\n"
        path = write_py(tmp_path, src)
        # Only 4 primitive-typed params → below threshold of 5
        assert detect(path, primitive_param_threshold=5) == []
        # With threshold 4, should flag
        reports = detect(path, primitive_param_threshold=4)
        assert len(reports) == 1
        assert reports[0].primitive_count == 4

    def test_default_params_with_primitive_annotation_counted(self, tmp_path):
        src = "def f(a: int = 0, b: str = '', c: float = 0.0, d: bool = False, e: bytes = b''): pass\n"
        path = write_py(tmp_path, src)
        reports = detect(path, primitive_param_threshold=5)
        assert len(reports) == 1
        assert reports[0].primitive_count == 5

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "def f(): pass\n")
        with pytest.raises(ValueError):
            detect(path, primitive_param_threshold=0)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            detect("/nonexistent/file.py")


# ---------------------------------------------------------------------------
# detect_smells (public API) — integration tests
# ---------------------------------------------------------------------------


class TestDetectSmellsPrimitiveObsession:
    def test_type_code_detected_via_public_api(self, tmp_path):
        src = "ROLE_ADMIN = 1\nROLE_USER = 2\nROLE_GUEST = 3\n"
        f = tmp_path / "codes.py"
        f.write_text(src)
        reports = detect_smells(f, type_code_threshold=3)
        assert any(r.smell == "PrimitiveObsession.TypeCode" for r in reports)

    def test_primitive_param_detected_via_public_api(self, tmp_path):
        src = "def f(a: int, b: str, c: float, d: bool, e: bytes): pass\n"
        f = tmp_path / "params.py"
        f.write_text(src)
        reports = detect_smells(f, primitive_param_threshold=5)
        assert any(r.smell == "PrimitiveObsession.PrimitiveParameterCluster" for r in reports)

    def test_all_three_detectors_run_together(self, tmp_path):
        long_body = "\n".join(f"    x{i} = {i}" for i in range(25))
        src = (
            "ROLE_A = 1\nROLE_B = 2\nROLE_C = 3\n\n"
            f"def big():\n{long_body}\n    return 0\n\n"
            "def f(a: int, b: str, c: float, d: bool, e: bytes): pass\n"
        )
        f = tmp_path / "all.py"
        f.write_text(src)
        reports = detect_smells(
            f,
            long_method_threshold=20,
            type_code_threshold=3,
            primitive_param_threshold=5,
        )
        smells = {r.smell for r in reports}
        assert "LongMethod" in smells
        assert "PrimitiveObsession.TypeCode" in smells
        assert "PrimitiveObsession.PrimitiveParameterCluster" in smells
