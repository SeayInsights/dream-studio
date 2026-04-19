"""Integration tests for on-changelog-nudge hook."""

from __future__ import annotations

import io
from unittest.mock import patch


def _run(handler, tmp_path, capsys, git_output: str = ""):
    import sys
    sys.stdin = io.StringIO("{}")

    mod = handler("on-changelog-nudge")

    with patch.object(mod, "_git", return_value=git_output), \
         patch.object(mod, "_find_project_root", return_value=tmp_path):
        mod.main()

    return capsys.readouterr().out


def test_nudges_when_source_changed_no_changelog(handler, tmp_path, capsys):
    git_status = " M hooks/lib/audit.py\n M hooks/handlers/on-pulse.py\n"
    out = _run(handler, tmp_path, capsys, git_status)
    assert "CHANGELOG" in out


def test_no_nudge_when_changelog_also_changed(handler, tmp_path, capsys):
    git_status = " M hooks/lib/audit.py\n M CHANGELOG.md\n"
    out = _run(handler, tmp_path, capsys, git_status)
    assert "CHANGELOG" not in out


def test_no_nudge_when_only_tests_changed(handler, tmp_path, capsys):
    git_status = " M tests/integration/test_audit.py\n"
    out = _run(handler, tmp_path, capsys, git_status)
    assert "CHANGELOG" not in out


def test_no_nudge_when_nothing_changed(handler, tmp_path, capsys):
    out = _run(handler, tmp_path, capsys, "")
    assert "CHANGELOG" not in out


def test_no_nudge_when_only_docs_changed(handler, tmp_path, capsys):
    git_status = " M docs/architecture.md\n M README.md\n"
    out = _run(handler, tmp_path, capsys, git_status)
    assert "CHANGELOG" not in out
