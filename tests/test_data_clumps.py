"""Tests for the Data Clumps detector."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import SmellReport, detect_smells
from src.data_clumps import (
    collect_field_data,
    collect_param_data,
    detect,
    detect_from_collected,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str, name: str = "sample.py") -> Path:
    f = tmp_path / name
    f.write_text(source)
    return f


# ---------------------------------------------------------------------------
# ParameterClump — unit tests
# ---------------------------------------------------------------------------


class TestParameterClump:
    def test_no_shared_params_not_flagged(self, tmp_path):
        src = (
            "def f(a, b, c): pass\n"
            "def g(x, y, z): pass\n"
        )
        path = write_py(tmp_path, src)
        assert detect(path, min_clump_size=3) == []

    def test_below_threshold_not_flagged(self, tmp_path):
        # 2 common params, threshold 3
        src = (
            "def f(host, port, timeout): pass\n"
            "def g(host, port, retries): pass\n"
        )
        path = write_py(tmp_path, src)
        assert detect(path, min_clump_size=3) == []

    def test_at_threshold_flagged(self, tmp_path):
        # Exactly 3 common params
        src = (
            "def connect(host, port, user): pass\n"
            "def reconnect(host, port, user): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2  # one per function

    def test_report_fields(self, tmp_path):
        src = (
            "def send(host, port, user, data): pass\n"
            "def recv(host, port, user, bufsize): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2
        names = {r.name for r in reports}
        assert "send" in names
        assert "recv" in names
        for r in reports:
            assert r.smell == "DataClump.ParameterClump"
            assert r.clump is not None
            assert len(r.clump) >= 3
            assert "parameter object" in r.message

    def test_self_not_counted(self, tmp_path):
        # self is excluded, so only 2 real shared params -> below threshold
        src = (
            "class A:\n"
            "    def f(self, host, port): pass\n"
            "    def g(self, host, port): pass\n"
        )
        path = write_py(tmp_path, src)
        assert detect(path, min_clump_size=3) == []

    def test_three_functions_all_flagged(self, tmp_path):
        src = (
            "def a(host, port, user): pass\n"
            "def b(host, port, user): pass\n"
            "def c(host, port, user): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        # Each function gets a report
        assert len(reports) == 3
        flagged_names = {r.name for r in reports}
        assert flagged_names == {"a", "b", "c"}

    def test_clump_tuple_is_sorted(self, tmp_path):
        src = (
            "def f(z_param, a_param, m_param): pass\n"
            "def g(z_param, a_param, m_param): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        for r in reports:
            assert list(r.clump) == sorted(r.clump)

    def test_typed_params_detected(self, tmp_path):
        src = (
            "def f(host: str, port: int, user: str): pass\n"
            "def g(host: str, port: int, user: str): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2

    def test_default_params_detected(self, tmp_path):
        src = (
            "def f(host='localhost', port=5432, user='admin'): pass\n"
            "def g(host='localhost', port=5432, user='admin'): pass\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "def f(a, b): pass\n")
        with pytest.raises(ValueError):
            detect(path, min_clump_size=1)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            detect("/nonexistent/file.py")


# ---------------------------------------------------------------------------
# FieldClump — unit tests
# ---------------------------------------------------------------------------


class TestFieldClump:
    def test_no_shared_fields_not_flagged(self, tmp_path):
        src = (
            "class A:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "        self.y = 2\n"
            "        self.z = 3\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self.a = 1\n"
            "        self.b = 2\n"
            "        self.c = 3\n"
        )
        path = write_py(tmp_path, src)
        assert detect(path, min_clump_size=3) == []

    def test_shared_instance_fields_flagged(self, tmp_path):
        src = (
            "class Connection:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.user = ''\n"
            "class Pool:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.user = ''\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2
        names = {r.name for r in reports}
        assert "Connection" in names
        assert "Pool" in names
        for r in reports:
            assert r.smell == "DataClump.FieldClump"
            assert r.clump is not None
            assert "shared class" in r.message

    def test_class_level_annotations_counted(self, tmp_path):
        src = (
            "class A:\n"
            "    host: str\n"
            "    port: int\n"
            "    user: str\n"
            "class B:\n"
            "    host: str\n"
            "    port: int\n"
            "    user: str\n"
        )
        path = write_py(tmp_path, src)
        reports = detect(path, min_clump_size=3)
        assert len(reports) == 2

    def test_below_threshold_not_flagged(self, tmp_path):
        src = (
            "class A:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.extra = None\n"
            "class B:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.other = None\n"
        )
        path = write_py(tmp_path, src)
        assert detect(path, min_clump_size=3) == []


# ---------------------------------------------------------------------------
# Cross-file detection — detect_from_collected
# ---------------------------------------------------------------------------


class TestCrossFileDetection:
    def test_parameter_clump_across_files(self, tmp_path):
        a = write_py(tmp_path, "def send(host, port, user): pass\n", "a.py")
        b = write_py(tmp_path, "def recv(host, port, user): pass\n", "b.py")

        param_data = collect_param_data(a) + collect_param_data(b)
        field_data = []
        reports = detect_from_collected(param_data, field_data, min_clump_size=3)

        assert len(reports) == 2
        files = {r.file for r in reports}
        assert str(a) in files
        assert str(b) in files

    def test_field_clump_across_files(self, tmp_path):
        src_a = (
            "class Conn:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.user = ''\n"
        )
        src_b = (
            "class Pool:\n"
            "    def __init__(self):\n"
            "        self.host = ''\n"
            "        self.port = 0\n"
            "        self.user = ''\n"
        )
        a = write_py(tmp_path, src_a, "a.py")
        b = write_py(tmp_path, src_b, "b.py")

        param_data = []
        field_data = collect_field_data(a) + collect_field_data(b)
        reports = detect_from_collected(param_data, field_data, min_clump_size=3)

        assert len(reports) == 2
        assert all(r.smell == "DataClump.FieldClump" for r in reports)

    def test_cross_file_message_includes_origin_file(self, tmp_path):
        a = write_py(tmp_path, "def f(host, port, user): pass\n", "a.py")
        b = write_py(tmp_path, "def g(host, port, user): pass\n", "b.py")

        param_data = collect_param_data(a) + collect_param_data(b)
        reports = detect_from_collected(param_data, [], min_clump_size=3)

        # Each report should mention the other function with its file
        for r in reports:
            assert "a.py" in r.message or "b.py" in r.message

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            detect_from_collected([], [], min_clump_size=1)


# ---------------------------------------------------------------------------
# detect_smells integration
# ---------------------------------------------------------------------------


class TestDetectSmellsDataClumps:
    def test_param_clump_detected_via_public_api(self, tmp_path):
        src = (
            "def connect(host, port, user): pass\n"
            "def reconnect(host, port, user): pass\n"
        )
        f = tmp_path / "c.py"
        f.write_text(src)
        reports = detect_smells(f, data_clump_size=3)
        assert any(r.smell == "DataClump.ParameterClump" for r in reports)

    def test_cross_file_clump_via_public_api(self, tmp_path):
        (tmp_path / "a.py").write_text("def f(host, port, user): pass\n")
        (tmp_path / "b.py").write_text("def g(host, port, user): pass\n")
        reports = detect_smells(tmp_path, data_clump_size=3)
        assert any(r.smell == "DataClump.ParameterClump" for r in reports)

    def test_all_detectors_together(self, tmp_path):
        long_body = "\n".join(f"    x{i} = {i}" for i in range(25))
        src = (
            "ROLE_A = 1\nROLE_B = 2\nROLE_C = 3\n\n"
            f"def big():\n{long_body}\n    return 0\n\n"
            "def connect(host, port, user): pass\n"
            "def reconnect(host, port, user): pass\n"
        )
        f = tmp_path / "all.py"
        f.write_text(src)
        reports = detect_smells(
            f,
            long_method_threshold=20,
            type_code_threshold=3,
            data_clump_size=3,
        )
        smells = {r.smell for r in reports}
        assert "LongMethod" in smells
        assert "PrimitiveObsession.TypeCode" in smells
        assert "DataClump.ParameterClump" in smells
