"""Tests for the migration risk classifier gate."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.gates.migration_risk import _is_risk_file, main


def test_is_risk_file_migration_sql():
    assert _is_risk_file("core/event_store/migrations/083_something.sql")


def test_is_risk_file_sqlite_bootstrap():
    assert _is_risk_file("core/config/sqlite_bootstrap.py")


def test_is_risk_file_pure_python_returns_false():
    assert not _is_risk_file("core/config/schema_coherence.py")
    assert not _is_risk_file("core/health/doctor.py")
    assert not _is_risk_file("tests/unit/test_schema_coherence_audit.py")


def test_main_returns_zero_on_no_risk_files(capsys):
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/health/doctor.py", "tests/unit/test_x.py"],
    ):
        result = main()
    assert result == 0


def test_main_returns_one_on_migration_change(capsys):
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/event_store/migrations/083_new.sql"],
    ):
        result = main()
    assert result == 1
    captured = capsys.readouterr()
    assert "MIGRATION RISK" in captured.out
    assert "083_new.sql" in captured.out
    assert "gh pr checks" in captured.out


def test_main_returns_one_on_sqlite_bootstrap_change(capsys):
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/config/sqlite_bootstrap.py"],
    ):
        result = main()
    assert result == 1
    captured = capsys.readouterr()
    assert "sqlite_bootstrap.py" in captured.out


def test_main_skips_in_ci_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/event_store/migrations/083_new.sql"],
    ):
        result = main()
    assert result == 0


def test_main_bypass_with_env_var(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("MIGRATION_RISK_ACKNOWLEDGED", "1")
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/event_store/migrations/083_new.sql"],
    ):
        result = main()
    assert result == 0
    captured = capsys.readouterr()
    assert "bypassing" in captured.out.lower()


def test_main_includes_platform_list(capsys):
    with patch(
        "core.gates.migration_risk._changed_files",
        return_value=["core/event_store/migrations/083_new.sql"],
    ):
        main()
    captured = capsys.readouterr()
    assert "ubuntu-latest" in captured.out
    assert "macos-latest" in captured.out
    assert "windows-latest" in captured.out
