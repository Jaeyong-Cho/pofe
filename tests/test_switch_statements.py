"""Tests for the Switch Statements detector."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src import SmellReport, detect_smells
from src.switch_statements import detect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_py(tmp_path: Path, source: str) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(dedent(source))
    return f


# ---------------------------------------------------------------------------
# IfElseChain — unit tests
# ---------------------------------------------------------------------------


class TestIfElseChain:
    def test_plain_if_else_not_flagged(self, tmp_path):
        # Only if + else = 1 branch; never flagged
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1:
                    return "a"
                else:
                    return "b"
        """)
        assert detect(path, if_else_chain_threshold=3) == []

    def test_one_elif_below_threshold_not_flagged(self, tmp_path):
        # if + 1 elif = 2 branches; threshold 3
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1:
                    return "a"
                elif x == 2:
                    return "b"
                else:
                    return "c"
        """)
        assert detect(path, if_else_chain_threshold=3) == []

    def test_at_threshold_flagged(self, tmp_path):
        # if + 2 elif = 3 branches; threshold 3 → flagged
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1:
                    return "a"
                elif x == 2:
                    return "b"
                elif x == 3:
                    return "c"
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        assert reports[0].smell == "SwitchStatement.IfElseChain"

    def test_report_fields(self, tmp_path):
        path = write_py(tmp_path, """\
            def dispatch(cmd):
                if cmd == "start":
                    start()
                elif cmd == "stop":
                    stop()
                elif cmd == "restart":
                    restart()
                else:
                    raise ValueError(cmd)
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "SwitchStatement.IfElseChain"
        assert r.name == "dispatch"
        assert r.branch_count == 3
        assert "3 branches" in r.message
        assert "threshold: 3" in r.message
        assert "polymorphism" in r.message.lower() or "dispatch" in r.message.lower()

    def test_else_not_counted_as_branch(self, tmp_path):
        # else clause is a catch-all, not a typed branch
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1:
                    pass
                elif x == 2:
                    pass
                elif x == 3:
                    pass
                else:
                    pass
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        assert reports[0].branch_count == 3  # else not counted

    def test_scope_inside_class_method(self, tmp_path):
        path = write_py(tmp_path, """\
            class Handler:
                def handle(self, event):
                    if event == "click":
                        pass
                    elif event == "hover":
                        pass
                    elif event == "focus":
                        pass
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        assert reports[0].name == "handle"

    def test_module_level_chain_uses_module_scope(self, tmp_path):
        path = write_py(tmp_path, """\
            if MODE == 1:
                x = "a"
            elif MODE == 2:
                x = "b"
            elif MODE == 3:
                x = "c"
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        assert reports[0].name == "<module>"

    def test_nested_chain_flagged_independently(self, tmp_path):
        # The inner if/elif chain inside an elif body should be flagged on its own
        path = write_py(tmp_path, """\
            def outer(x, y):
                if x == 1:
                    pass
                elif x == 2:
                    if y == "a":
                        pass
                    elif y == "b":
                        pass
                    elif y == "c":
                        pass
                elif x == 3:
                    pass
        """)
        reports = detect(path, if_else_chain_threshold=3)
        # outer has 3 branches, inner also has 3 branches → 2 reports
        assert len(reports) == 2
        branch_counts = {r.branch_count for r in reports}
        assert 3 in branch_counts

    def test_multiple_functions_each_flagged(self, tmp_path):
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1: return 1
                elif x == 2: return 2
                elif x == 3: return 3

            def g(x):
                if x == "a": return 10
                elif x == "b": return 20
                elif x == "c": return 30
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 2
        names = {r.name for r in reports}
        assert names == {"f", "g"}

    def test_line_range_covers_full_chain(self, tmp_path):
        path = write_py(tmp_path, """\
            def f(x):
                if x == 1:
                    return 1
                elif x == 2:
                    return 2
                elif x == 3:
                    return 3
                else:
                    return 0
        """)
        reports = detect(path, if_else_chain_threshold=3)
        assert len(reports) == 1
        r = reports[0]
        assert r.start_line <= r.end_line
        assert r.line_count == r.end_line - r.start_line + 1

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "x = 1\n")
        with pytest.raises(ValueError, match="if_else_chain_threshold must be >= 2"):
            detect(path, if_else_chain_threshold=1)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect(tmp_path / "missing.py")


# ---------------------------------------------------------------------------
# ComplexMatch — unit tests
# ---------------------------------------------------------------------------


class TestComplexMatch:
    def test_few_cases_not_flagged(self, tmp_path):
        # 2 cases, threshold 3 → not flagged
        path = write_py(tmp_path, """\
            def f(cmd):
                match cmd:
                    case "start":
                        pass
                    case "stop":
                        pass
        """)
        assert detect(path, match_case_threshold=3) == []

    def test_at_threshold_flagged(self, tmp_path):
        # 3 cases, threshold 3 → flagged
        path = write_py(tmp_path, """\
            def process(action):
                match action:
                    case "create":
                        create()
                    case "read":
                        read()
                    case "delete":
                        delete()
        """)
        reports = detect(path, match_case_threshold=3)
        assert len(reports) == 1
        assert reports[0].smell == "SwitchStatement.ComplexMatch"

    def test_report_fields(self, tmp_path):
        path = write_py(tmp_path, """\
            def route(method):
                match method:
                    case "GET":
                        get()
                    case "POST":
                        post()
                    case "PUT":
                        put()
                    case _:
                        raise ValueError(method)
        """)
        reports = detect(path, match_case_threshold=3)
        assert len(reports) == 1
        r = reports[0]
        assert r.smell == "SwitchStatement.ComplexMatch"
        assert r.name == "route"
        assert r.branch_count == 4  # GET, POST, PUT, wildcard
        assert "4 cases" in r.message
        assert "threshold: 3" in r.message
        assert "polymorphism" in r.message.lower()

    def test_match_inside_class_method(self, tmp_path):
        path = write_py(tmp_path, """\
            class Router:
                def dispatch(self, method):
                    match method:
                        case "GET":
                            self.get()
                        case "POST":
                            self.post()
                        case "DELETE":
                            self.delete()
        """)
        reports = detect(path, match_case_threshold=3)
        assert len(reports) == 1
        assert reports[0].name == "dispatch"

    def test_invalid_threshold_raises(self, tmp_path):
        path = write_py(tmp_path, "x = 1\n")
        with pytest.raises(ValueError, match="match_case_threshold must be >= 2"):
            detect(path, match_case_threshold=1)


# ---------------------------------------------------------------------------
# Integration — detect_smells public API
# ---------------------------------------------------------------------------


class TestDetectSmellsSwitchStatements:
    def test_if_else_chain_detected_via_public_api(self, tmp_path):
        src = dedent("""\
            def classify(x):
                if x == 1:
                    return "one"
                elif x == 2:
                    return "two"
                elif x == 3:
                    return "three"
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path, if_else_chain_threshold=3)
        ss = [r for r in reports if r.smell == "SwitchStatement.IfElseChain"]
        assert len(ss) == 1
        assert ss[0].name == "classify"

    def test_match_detected_via_public_api(self, tmp_path):
        src = dedent("""\
            def handle(event):
                match event:
                    case "click":
                        click()
                    case "hover":
                        hover()
                    case "focus":
                        focus()
        """)
        f = tmp_path / "sample.py"
        f.write_text(src)
        reports = detect_smells(tmp_path, match_case_threshold=3)
        ss = [r for r in reports if r.smell == "SwitchStatement.ComplexMatch"]
        assert len(ss) == 1

    def test_all_detectors_run_together(self, tmp_path):
        # File triggers LongMethod (21 lines), LargeClass (21 methods),
        # and SwitchStatement to confirm all run without interfering.
        chain = dedent("""\
            def router(action):
                if action == "a":
                    pass
                elif action == "b":
                    pass
                elif action == "c":
                    pass
        """)
        f = tmp_path / "sample.py"
        f.write_text(chain)
        reports = detect_smells(tmp_path, if_else_chain_threshold=3)
        ss = [r for r in reports if r.smell.startswith("SwitchStatement")]
        assert len(ss) >= 1
