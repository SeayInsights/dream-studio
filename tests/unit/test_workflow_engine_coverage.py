"""Coverage supplement for workflow_engine — targets lines not hit by test_workflow_state.py.

Covers: _file_lock, _extract_node_ids fallback, _coerce quality-score alias,
_check_context_budget branches, _evaluate != string path, condition exception path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

_LIB_DIR = Path(__file__).resolve().parents[2] / "hooks" / "lib"
if str(_LIB_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR.parent))

from lib.context_handoff import HANDOFF_PCT, URGENT_PCT  # noqa: E402


def _load(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _LIB_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


eng = _load("workflow_engine")


# ── _file_lock ─────────────────────────────────────────────────────────


class TestFileLock:
    def test_acquires_and_releases(self, tmp_path: Path) -> None:
        lock = tmp_path / "test.lock"
        with eng._file_lock(lock):
            assert lock.exists()
        assert not lock.exists()

    def test_lock_file_removed_on_exception(self, tmp_path: Path) -> None:
        lock = tmp_path / "test.lock"
        with pytest.raises(ValueError):
            with eng._file_lock(lock):
                assert lock.exists()
                raise ValueError("boom")
        assert not lock.exists()

    def test_stale_lock_force_acquired_on_timeout(self, tmp_path: Path) -> None:
        lock = tmp_path / "stale.lock"
        lock.write_text("99999")  # pre-existing stale lock

        # Patch monotonic so deadline is immediately exceeded
        call_count = 0

        def fast_clock():
            nonlocal call_count
            call_count += 1
            # First call returns 0 (start), second returns 100 (past deadline)
            return 0.0 if call_count == 1 else 100.0

        with patch("lib.workflow_engine.time.monotonic", side_effect=fast_clock):
            with eng._file_lock(lock, timeout=5.0):
                assert lock.exists()
        assert not lock.exists()


# ── _extract_node_ids fallback ─────────────────────────────────────────


class TestExtractNodeIds:
    def test_fallback_parser_reads_node_ids(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "nodes:\n- id: build\n- id: test\n- id: deploy\n",
            encoding="utf-8",
        )
        with patch.object(eng, "parse_workflow", side_effect=Exception("fail")):
            ids = eng._extract_node_ids(str(yaml))
        assert ids == ["build", "test", "deploy"]

    def test_fallback_skips_block_scalar_content(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "nodes:\n- id: real\n  prompt: |\n    - id: fake\n- id: also_real\n",
            encoding="utf-8",
        )
        with patch.object(eng, "parse_workflow", side_effect=Exception("fail")):
            ids = eng._extract_node_ids(str(yaml))
        assert "real" in ids
        assert "also_real" in ids
        assert "fake" not in ids

    def test_uses_parse_workflow_when_available(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text("nodes:\n- id: only\n", encoding="utf-8")
        with patch.object(
            eng,
            "parse_workflow",
            return_value={"nodes": [{"id": "only"}]},
        ):
            ids = eng._extract_node_ids(str(yaml))
        assert "only" in ids


# ── _coerce quality-score alias ────────────────────────────────────────


class TestCoerceQualityScore:
    def test_reads_score_from_file(self, tmp_path: Path) -> None:
        score_file = tmp_path / "quality-score.json"
        score_file.write_text(json.dumps({"overall_score": 87.5}), encoding="utf-8")
        with patch("lib.workflow_engine.paths.meta_dir", return_value=tmp_path):
            result = eng._coerce("quality-score")
        assert result == 87.5

    def test_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        with patch("lib.workflow_engine.paths.meta_dir", return_value=tmp_path):
            result = eng._coerce("quality-score")
        assert result == 0.0

    def test_returns_zero_on_malformed_json(self, tmp_path: Path) -> None:
        (tmp_path / "quality-score.json").write_text("not json", encoding="utf-8")
        with patch("lib.workflow_engine.paths.meta_dir", return_value=tmp_path):
            result = eng._coerce("quality-score")
        assert result == 0.0


# ── _check_context_budget ──────────────────────────────────────────────


class TestCheckContextBudget:
    def test_no_context_file_returns_none(self, tmp_path: Path) -> None:
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            assert eng._check_context_budget(2) is None

    def test_zero_pct_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "context.json").write_text(json.dumps({"pct": 0}), encoding="utf-8")
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            assert eng._check_context_budget(1) is None

    def test_below_handoff_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "context.json").write_text(json.dumps({"pct": 50}), encoding="utf-8")
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            assert eng._check_context_budget(1) is None

    def test_urgent_pct_returns_block(self, tmp_path: Path) -> None:
        (tmp_path / "context.json").write_text(
            json.dumps({"pct": URGENT_PCT + 1}), encoding="utf-8"
        )
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            result = eng._check_context_budget(3)
        assert result == "block"

    def test_handoff_pct_non_interactive_blocks(self, tmp_path: Path) -> None:
        mid = (HANDOFF_PCT + URGENT_PCT) / 2
        (tmp_path / "context.json").write_text(json.dumps({"pct": mid}), encoding="utf-8")
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            with patch("sys.stdin.isatty", return_value=False):
                result = eng._check_context_budget(2)
        assert result == "block"

    def test_malformed_context_json_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "context.json").write_text("bad", encoding="utf-8")
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            assert eng._check_context_budget(1) is None

    def test_used_pct_field_alias(self, tmp_path: Path) -> None:
        (tmp_path / "context.json").write_text(json.dumps({"used_pct": 10}), encoding="utf-8")
        with patch("lib.workflow_engine.paths.state_dir", return_value=tmp_path):
            assert eng._check_context_budget(1) is None


# ── _evaluate string != branch ─────────────────────────────────────────


class TestEvaluateStringNotEqual:
    def _wf(self, nodes):
        return {"nodes": nodes}

    def test_string_ne_true(self) -> None:
        wf = self._wf({"n": {"output": "FAILED"}})
        assert eng._evaluate("{{n.output}} != PASSED", wf) is True

    def test_string_ne_false_exact(self) -> None:
        wf = self._wf({"n": {"output": "PASSED"}})
        assert eng._evaluate("{{n.output}} != PASSED", wf) is False

    def test_string_ne_false_prefix(self) -> None:
        wf = self._wf({"n": {"output": "PASSED: with detail"}})
        assert eng._evaluate("{{n.output}} != PASSED", wf) is False

    def test_gt_lt_numeric(self) -> None:
        wf = self._wf({"n": {"value": "5"}})
        assert eng._evaluate("{{n.value}} > 3", wf) is True
        assert eng._evaluate("{{n.value}} < 3", wf) is False
        assert eng._evaluate("{{n.value}} <= 5", wf) is True

    def test_non_numeric_gt_returns_false(self) -> None:
        # Covers line 204: found_op is ">" but both sides are strings → return False
        wf = self._wf({"n": {"value": "abc"}})
        assert eng._evaluate("{{n.value}} > xyz", wf) is False


# ── _extract_node_ids: empty-line skip (line 82) ───────────────────────


class TestExtractNodeIdsEmptyLine:
    def test_empty_lines_skipped_in_fallback(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "nodes:\n\n- id: step1\n\n- id: step2\n",
            encoding="utf-8",
        )
        with patch.object(eng, "parse_workflow", side_effect=Exception("fail")):
            ids = eng._extract_node_ids(str(yaml))
        assert "step1" in ids
        assert "step2" in ids


# ── _file_lock: finally-block unlink OSError (lines 60-61) ────────────


class TestFileLockFinallyOSError:
    def test_unlink_oserror_in_finally_swallowed(self, tmp_path: Path) -> None:
        lock = tmp_path / "test.lock"
        with patch.object(Path, "unlink", side_effect=OSError("unlink blocked")):
            with eng._file_lock(lock):
                pass  # finally: unlink raises OSError → swallowed (lines 60-61)


# ── _compute_ready_nodes condition exception ───────────────────────────


class TestComputeReadyNodesEdgeCases:
    def test_condition_exception_skips_node(self) -> None:
        yaml_nodes = {"a": {"condition": "{{score.value}} >= 90"}}
        state_nodes = {"a": {"status": "pending"}}
        wf = {"nodes": {"score": {"value": "50"}}}
        with patch("lib.workflow_engine._evaluate", side_effect=RuntimeError("oops")):
            ready, skipped = eng._compute_ready_nodes(yaml_nodes, state_nodes, wf)
        assert "a" not in ready
        assert "a" in skipped

    def test_condition_exception_via_module_patch(self) -> None:
        # Patches the function on the loaded module object (not via lib.* path)
        # so the running code sees the exception — covers lines 314-315
        yaml_nodes = {"a": {"condition": "expr"}}
        state_nodes = {"a": {"status": "pending"}}
        wf = {"nodes": {}}
        with patch.object(eng, "_evaluate", side_effect=RuntimeError("boom")):
            ready, skipped = eng._compute_ready_nodes(yaml_nodes, state_nodes, wf)
        assert "a" not in ready
        assert "a" in skipped
