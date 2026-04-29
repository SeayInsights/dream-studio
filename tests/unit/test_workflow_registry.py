"""Tests for hooks/lib/workflow_registry.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hooks"))

from lib.workflow_registry import (  # noqa: E402
    format_registry_table,
    list_workflows,
    _fmt_tokens,
    _fmt_last_run,
)
from datetime import datetime, timezone, timedelta


def _write(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


class TestListWorkflows:
    def test_entry_per_yaml(self, tmp_path):
        _write(tmp_path / "alpha.yaml", {"name": "alpha", "description": "A", "nodes": []})
        _write(tmp_path / "beta.yaml", {"name": "beta", "description": "B", "nodes": []})
        result = list_workflows(tmp_path)
        assert len(result) == 2
        assert {w["name"] for w in result} == {"alpha", "beta"}

    def test_fallback_name_from_stem(self, tmp_path):
        _write(tmp_path / "no-name.yaml", {"nodes": []})
        assert list_workflows(tmp_path)[0]["name"] == "no-name"

    def test_fallback_description(self, tmp_path):
        _write(tmp_path / "bare.yaml", {"name": "bare", "nodes": []})
        assert list_workflows(tmp_path)[0]["description"] == "(no description)"

    def test_auto_discovers_new_file(self, tmp_path):
        _write(tmp_path / "first.yaml", {"name": "first", "nodes": []})
        assert len(list_workflows(tmp_path)) == 1
        _write(tmp_path / "second.yaml", {"name": "second", "nodes": []})
        assert len(list_workflows(tmp_path)) == 2

    def test_empty_dir_returns_empty(self, tmp_path):
        assert list_workflows(tmp_path) == []

    def test_tokens_none_when_absent(self, tmp_path):
        _write(tmp_path / "x.yaml", {"name": "x", "nodes": [{"id": "n1"}]})
        assert list_workflows(tmp_path)[0]["estimated_tokens"] is None

    def test_tokens_summed(self, tmp_path):
        _write(tmp_path / "x.yaml", {"name": "x", "nodes": [
            {"id": "n1", "estimated_tokens": 1000},
            {"id": "n2", "estimated_tokens": 500},
        ]})
        assert list_workflows(tmp_path)[0]["estimated_tokens"] == 1500

    def test_block_scalar_description_parsed(self, tmp_path):
        raw = "name: flow\ndescription: >\n  Multi-line\n  description here\nnodes: []\n"
        (tmp_path / "flow.yaml").write_text(raw, encoding="utf-8")
        result = list_workflows(tmp_path)
        assert "Multi-line" in result[0]["description"]

    def test_run_count_defaults_to_zero(self, tmp_path):
        _write(tmp_path / "x.yaml", {"name": "x", "nodes": []})
        assert list_workflows(tmp_path)[0]["run_count"] == 0


class TestFormatRegistryTable:
    def _wf(self, name="test", desc="A description", tok=None, last=None, rc=0):
        return {"name": name, "description": desc, "yaml_path": "/x.yaml",
                "estimated_tokens": tok, "last_run": last, "run_count": rc}

    def test_empty_says_no_workflows(self):
        assert "No workflows" in format_registry_table([])

    def test_contains_name_and_description(self):
        out = format_registry_table([self._wf("hotfix", "Fast fix")])
        assert "hotfix" in out and "Fast fix" in out

    def test_dash_for_missing_tokens(self):
        assert "—" in format_registry_table([self._wf(tok=None)])

    def test_tokens_formatted_as_k(self):
        assert "2k" in format_registry_table([self._wf(tok=2000)])

    def test_never_for_no_last_run(self):
        assert "never" in format_registry_table([self._wf(last=None)])

    def test_run_count_shown(self):
        assert "7" in format_registry_table([self._wf(rc=7)])


class TestHelpers:
    def test_fmt_tokens_none(self):
        assert _fmt_tokens(None) == "—"

    def test_fmt_tokens_small(self):
        assert _fmt_tokens(500) == "500"

    def test_fmt_tokens_k(self):
        assert _fmt_tokens(3000) == "3k"

    def test_fmt_last_run_none(self):
        now = datetime.now(timezone.utc)
        assert _fmt_last_run(None, now) == "never"

    def test_fmt_last_run_recent(self):
        now = datetime.now(timezone.utc)
        lr = {"finished_at": (now - timedelta(hours=2)).isoformat()}
        assert "2h ago" in _fmt_last_run(lr, now)
