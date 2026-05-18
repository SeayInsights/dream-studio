from __future__ import annotations

import pytest

from integrations.installer.base import FileOp, FileOpPlan, InstallerBase, RefusalError
from pathlib import Path


def test_refusal_error_is_value_error():
    with pytest.raises(ValueError):
        raise RefusalError("test")


def test_file_op_plan_summary_has_expected_keys(tmp_path):
    op = FileOp(
        target=tmp_path / "test.md",
        op="create",
        backup_required=False,
        source_hash="abc",
        reason="test",
        safety_notes="safe",
    )
    plan = FileOpPlan(ops=[op], tool="claude_code", scope="user")
    summary = plan.summary()
    assert len(summary) == 1
    assert summary[0]["target"] == str(tmp_path / "test.md")
    assert summary[0]["op"] == "create"
    assert summary[0]["backup_required"] is False
    assert summary[0]["reason"] == "test"


def test_installer_base_plan_raises():
    installer = InstallerBase()
    with pytest.raises(NotImplementedError):
        installer.plan()


def test_installer_base_install_raises_refusal_on_bad_mode():
    installer = InstallerBase()
    with pytest.raises(RefusalError):
        installer.install("approve")


def test_installer_base_install_raises_refusal_on_empty_mode():
    installer = InstallerBase()
    with pytest.raises(RefusalError):
        installer.install("")


def test_installer_base_install_dry_run_raises_not_implemented():
    installer = InstallerBase()
    with pytest.raises(NotImplementedError):
        installer.install("dry_run")


def test_installer_base_install_execute_raises_not_implemented():
    installer = InstallerBase()
    with pytest.raises(NotImplementedError):
        installer.install("execute")
