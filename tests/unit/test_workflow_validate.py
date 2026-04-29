"""Tests for workflow_validate.py — targeting 46 uncovered lines.

Covers: _split_kv no-colon (100), node flush on section switch (56-57, 61-62),
validate() error branches (145, 147, 151, 158, 164, 172, 174, 183, 187-194, 205),
main() CLI (232-264).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "hooks"
_LIB_DIR = _HOOKS_DIR / "lib"
_VALIDATE_PY = _LIB_DIR / "workflow_validate.py"

if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


def _load() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("workflow_validate", _VALIDATE_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["workflow_validate"] = mod
    spec.loader.exec_module(mod)
    return mod


wv = _load()


# ── _split_kv (line 100) ──────────────────────────────────────────────────


class TestSplitKv:
    def test_no_colon_returns_empty_val(self) -> None:
        key, val = wv._split_kv("no-colon-here")
        assert key == "no-colon-here"
        assert val == ""

    def test_colon_with_value(self) -> None:
        key, val = wv._split_kv("name: workflow-test")
        assert key == "name"
        assert val == "workflow-test"

    def test_multiple_colons_splits_on_first(self) -> None:
        key, val = wv._split_kv("url: http://example.com")
        assert key == "url"
        assert val == "http://example.com"


# ── parse_workflow — node flush on section switch (lines 56-57, 61-62) ───


class TestParseWorkflowNodeFlush:
    def test_node_flushed_when_gates_section_follows(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "name: flush-test\n"
            "nodes:\n"
            "  - id: alpha\n"
            "    skill: foo\n"
            "gates:\n"
            "  my_gate:\n"
            "    condition: ready\n",
            encoding="utf-8",
        )
        data = wv.parse_workflow(str(yaml))
        assert any(n["id"] == "alpha" for n in data["nodes"])
        assert "my_gate" in data["gates"]

    def test_node_flushed_when_second_nodes_key(self, tmp_path: Path) -> None:
        # Exercises lines 61-62: `nodes:` at indent 0 while node is pending
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "name: double-nodes\n"
            "nodes:\n"
            "  - id: first\n"
            "    skill: foo\n"
            "nodes:\n"
            "  - id: second\n"
            "    skill: bar\n",
            encoding="utf-8",
        )
        data = wv.parse_workflow(str(yaml))
        ids = [n["id"] for n in data["nodes"]]
        assert "first" in ids
        assert "second" in ids

    def test_block_scalar_skipped(self, tmp_path: Path) -> None:
        yaml = tmp_path / "wf.yaml"
        yaml.write_text(
            "name: block\n"
            "nodes:\n"
            "  - id: step\n"
            "    prompt: |\n"
            "      multi\n"
            "      line\n",
            encoding="utf-8",
        )
        data = wv.parse_workflow(str(yaml))
        assert any(n["id"] == "step" for n in data["nodes"])


# ── validate() — all error branches ──────────────────────────────────────


class TestValidateErrors:
    def _no_skill_root(self, tmp_path: Path) -> Path:
        return tmp_path  # no skills/ subdir → any skill lookup will fail

    def test_node_missing_skill_and_command(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a"}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("needs 'skill' or 'command'" in e for e in errors)

    def test_node_has_both_skill_and_command(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "command": "echo hi"}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("has both 'skill' and 'command'" in e for e in errors)

    def test_depends_on_unknown_node(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "depends_on": ["ghost"]}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any('depends_on "ghost"' in e for e in errors)

    def test_gate_not_in_gates_section(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "gate": "no_gate"}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any('"no_gate" not in gates' in e for e in errors)

    def test_skill_file_not_found(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "missing_skill"}], "gates": {}}
        errors = wv.validate(data, tmp_path)
        assert any("missing_skill" in e and "not found" in e for e in errors)

    def test_on_failure_not_string(self, tmp_path: Path) -> None:
        data = {
            "nodes": [{"id": "a", "skill": "foo"}],
            "gates": {},
            "on_failure": ["abort"],
        }
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("on_failure must be a string" in e for e in errors)

    def test_on_failure_unknown_string(self, tmp_path: Path) -> None:
        data = {
            "nodes": [{"id": "a", "skill": "foo"}],
            "gates": {},
            "on_failure": "restart",
        }
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any('"restart"' in e for e in errors)

    def test_on_failure_abort_is_valid(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# foo")
        data = {
            "nodes": [{"id": "a", "skill": "foo"}],
            "gates": {},
            "on_failure": "abort",
        }
        errors = wv.validate(data, tmp_path)
        assert not errors

    def test_on_failure_node_id_is_valid(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# foo")
        data = {
            "nodes": [{"id": "a", "skill": "foo"}],
            "gates": {},
            "on_failure": "a",
        }
        errors = wv.validate(data, tmp_path)
        assert not errors

    def test_timeout_zero_is_invalid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "timeout_seconds": 0}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("timeout_seconds must be a positive integer" in e for e in errors)

    def test_timeout_negative_is_invalid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "timeout_seconds": -5}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("timeout_seconds must be a positive integer" in e for e in errors)

    def test_timeout_positive_is_valid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "timeout_seconds": 30}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert not any("timeout_seconds" in e for e in errors)

    def test_retry_not_dict(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "retry": "yes"}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("retry must be a mapping" in e for e in errors)

    def test_retry_missing_max(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "retry": {}}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("retry.max is required" in e for e in errors)

    def test_retry_max_zero_invalid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "retry": {"max": 0}}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("retry.max must be a positive integer" in e for e in errors)

    def test_retry_max_negative_invalid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "retry": {"max": -1}}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("retry.max must be a positive integer" in e for e in errors)

    def test_retry_max_valid(self, tmp_path: Path) -> None:
        data = {"nodes": [{"id": "a", "skill": "foo", "retry": {"max": 3}}], "gates": {}}
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert not any("retry must" in e or "retry.max" in e for e in errors)

    def test_cycle_detected(self, tmp_path: Path) -> None:
        data = {
            "nodes": [
                {"id": "a", "skill": "foo", "depends_on": ["b"]},
                {"id": "b", "skill": "bar", "depends_on": ["a"]},
            ],
            "gates": {},
        }
        errors = wv.validate(data, self._no_skill_root(tmp_path))
        assert any("Cycle detected" in e for e in errors)

    def test_depends_on_string_hits_cycle_detection(self, tmp_path: Path) -> None:
        # depends_on as a plain string → line 205 (isinstance str → [deps])
        skill_dir = tmp_path / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# foo")
        skill_dir2 = tmp_path / "skills" / "bar"
        skill_dir2.mkdir(parents=True)
        (skill_dir2 / "SKILL.md").write_text("# bar")
        data = {
            "nodes": [
                {"id": "a", "skill": "foo"},
                {"id": "b", "skill": "bar", "depends_on": "a"},  # string, not list
            ],
            "gates": {},
        }
        errors = wv.validate(data, tmp_path)
        assert not errors  # valid topology, string dep resolves correctly


# ── main() CLI (lines 232-264) ────────────────────────────────────────────


class TestMain:
    def test_valid_workflow_exits_zero(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "build"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# build")
        wf = tmp_path / "workflow.yaml"
        wf.write_text(
            "name: ci\n"
            "nodes:\n"
            "  - id: step1\n"
            "    skill: build\n",
            encoding="utf-8",
        )
        with patch("sys.argv", ["workflow_validate", str(wf), "--plugin-root", str(tmp_path)]):
            with pytest.raises(SystemExit) as exc:
                wv.main()
        assert exc.value.code == 0

    def test_invalid_workflow_exits_one(self, tmp_path: Path) -> None:
        wf = tmp_path / "bad.yaml"
        wf.write_text("name: bad\nnodes:\n  - id: a\n", encoding="utf-8")
        with patch("sys.argv", ["workflow_validate", str(wf), "--plugin-root", str(tmp_path)]):
            with pytest.raises(SystemExit) as exc:
                wv.main()
        assert exc.value.code == 1

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.yaml"
        with patch("sys.argv", ["workflow_validate", str(missing)]):
            with pytest.raises(SystemExit) as exc:
                wv.main()
        assert exc.value.code == 1

    def test_plugin_root_fallback_when_paths_raises(self, tmp_path: Path) -> None:
        # No --plugin-root; paths.plugin_root() raises → falls back to file's grandparent
        wf = tmp_path / "wf.yaml"
        wf.write_text(
            "name: t\nnodes:\n  - id: x\n    skill: nonexistent_xyz\n",
            encoding="utf-8",
        )
        with patch("sys.argv", ["workflow_validate", str(wf)]):
            with patch.object(wv.paths, "plugin_root", side_effect=RuntimeError("no root")):
                with pytest.raises(SystemExit) as exc:
                    wv.main()
        assert exc.value.code == 1  # skill not found → FAIL

    def test_plugin_root_from_paths_module(self, tmp_path: Path) -> None:
        # No --plugin-root; paths.plugin_root() returns tmp_path
        wf = tmp_path / "wf.yaml"
        wf.write_text(
            "name: t\nnodes:\n  - id: x\n    skill: nonexistent_xyz\n",
            encoding="utf-8",
        )
        with patch("sys.argv", ["workflow_validate", str(wf)]):
            with patch.object(wv.paths, "plugin_root", return_value=tmp_path):
                with pytest.raises(SystemExit) as exc:
                    wv.main()
        assert exc.value.code == 1  # skill nonexistent_xyz not found

    def test_ok_output_includes_node_count(self, tmp_path: Path, capsys) -> None:
        skill_dir = tmp_path / "skills" / "lint"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# lint")
        wf = tmp_path / "workflow.yaml"
        wf.write_text(
            "name: ok-test\n"
            "gates:\n"
            "  done:\n"
            "    condition: true\n"
            "nodes:\n"
            "  - id: n1\n"
            "    skill: lint\n"
            "    gate: done\n",
            encoding="utf-8",
        )
        with patch("sys.argv", ["workflow_validate", str(wf), "--plugin-root", str(tmp_path)]):
            with pytest.raises(SystemExit) as exc:
                wv.main()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "1 nodes" in out
        assert "1 gates" in out
