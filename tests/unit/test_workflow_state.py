"""Tests for workflow_engine._evaluate, _resolve_ref, _coerce, and condition gating."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR.parent))

def _load(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _LIB_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

mod = _load("workflow_engine")
_evaluate = mod._evaluate
_resolve_ref = mod._resolve_ref
_coerce = mod._coerce


def _wf(nodes: dict) -> dict:
    return {"nodes": nodes}


class TestResolveRef:
    def test_existing_field(self):
        wf = _wf({"build": {"output": "PASSED"}})
        assert _resolve_ref("build.output", wf) == "PASSED"

    def test_missing_node(self):
        wf = _wf({})
        assert _resolve_ref("missing.output", wf) is None

    def test_no_dot(self):
        assert _resolve_ref("nodot", _wf({})) is None

    def test_missing_field_returns_empty(self):
        wf = _wf({"build": {}})
        assert _resolve_ref("build.output", wf) == ""


class TestCoerce:
    def test_int(self):
        assert _coerce("42") == 42

    def test_float(self):
        assert _coerce("3.14") == 3.14

    def test_string(self):
        assert _coerce("hello") == "hello"

    def test_empty(self):
        assert _coerce("") == ""


class TestEvaluate:
    def test_simple_equal(self):
        wf = _wf({"n": {"output": "PASSED"}})
        assert _evaluate("{{n.output}} == PASSED", wf) is True

    def test_simple_not_equal(self):
        wf = _wf({"n": {"output": "BLOCKED"}})
        assert _evaluate("{{n.output}} == PASSED", wf) is False

    def test_prefix_match_blocked(self):
        wf = _wf({"n": {"output": "BLOCKED: 2 issues found"}})
        assert _evaluate("{{n.output}} == BLOCKED", wf) is True

    def test_eq_inside_output_does_not_corrupt(self):
        """BP-R4-06 regression: == inside resolved value must not split the expression."""
        wf = _wf({"n": {"output": "PASSED: cost==2 found"}})
        assert _evaluate("{{n.output}} == PASSED", wf) is True

    def test_blocked_with_eq_in_value(self):
        wf = _wf({"n": {"output": "BLOCKED: a==b issue"}})
        assert _evaluate("{{n.output}} == BLOCKED", wf) is True

    def test_mismatch_with_eq_in_value(self):
        wf = _wf({"n": {"output": "BLOCKED: a==b issue"}})
        assert _evaluate("{{n.output}} == PASSED", wf) is False

    def test_unresolved_ref_returns_false(self):
        assert _evaluate("{{missing.output}} == PASSED", _wf({})) is False

    def test_malformed_template_returns_false(self):
        assert _evaluate("{{unclosed == PASSED", _wf({})) is False

    def test_numeric_comparison(self):
        wf = _wf({"score": {"value": "85"}})
        assert _evaluate("{{score.value}} >= 80", wf) is True

    def test_not_equal(self):
        wf = _wf({"n": {"output": "FAILED"}})
        assert _evaluate("{{n.output}} != PASSED", wf) is True

    def test_no_operator_truthy(self):
        wf = _wf({"n": {"output": "BLOCKED: something"}})
        assert _evaluate("{{n.output}}", wf) is True

    def test_no_operator_empty_is_false(self):
        wf = _wf({"n": {"output": ""}})
        assert _evaluate("{{n.output}}", wf) is False


class TestTraceabilityFileSizeLimit:
    def test_file_too_large_returns_error(self, tmp_path):
        """BP-R3-04 regression: files over MAX_FILE_SIZE must be rejected."""
        import importlib.util as _ilu
        import sys as _sys
        _trace_spec = _ilu.spec_from_file_location(
            "traceability_test",
            Path(__file__).resolve().parents[2] / "hooks" / "lib" / "traceability.py"
        )
        assert _trace_spec and _trace_spec.loader
        trace_mod = _ilu.module_from_spec(_trace_spec)
        _sys.modules["traceability_test"] = trace_mod
        _trace_spec.loader.exec_module(trace_mod)

        big_file = tmp_path / "big.yaml"
        # Write a file just over the 5MB limit
        big_file.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        errors = trace_mod.validate_registry(big_file)
        assert any("too large" in e.lower() or "large" in e.lower() for e in errors)

    def test_empty_file_returns_error(self, tmp_path):
        import importlib.util as _ilu
        import sys as _sys
        _trace_spec = _ilu.spec_from_file_location(
            "traceability_test2",
            Path(__file__).resolve().parents[2] / "hooks" / "lib" / "traceability.py"
        )
        assert _trace_spec and _trace_spec.loader
        trace_mod = _ilu.module_from_spec(_trace_spec)
        _sys.modules["traceability_test2"] = trace_mod
        _trace_spec.loader.exec_module(trace_mod)

        empty = tmp_path / "empty.yaml"
        empty.write_bytes(b"")
        errors = trace_mod.validate_registry(empty)
        assert any("empty" in e.lower() for e in errors)
