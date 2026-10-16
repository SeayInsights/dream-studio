"""An install writes only into its Claude Code root, the Dream Studio home and the named
repository's .git/hooks; a plan that reaches anywhere else is refused before any write.

The root is resolved in one place and paths are built in many; a plan that writes
outside the root means the two disagreed, the class of bug that once wrote one
identity's settings while the environment named another.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.installer.base import FileOp, FileOpPlan, RefusalError
from integrations.installer.claude_code import ClaudeCodeInstaller


def _installer(tmp_path: Path) -> ClaudeCodeInstaller:
    root = tmp_path / "claude-root"
    root.mkdir()
    return ClaudeCodeInstaller(root, "user", ds_home=tmp_path / "ds-home", hook_mode="module")


def _plan_writing(target: Path) -> FileOpPlan:
    return FileOpPlan(
        ops=[
            FileOp(
                target=target,
                op="create",
                backup_required=False,
                source_hash="",
                reason="x",
                source_content="x",
            )
        ],
        tool="claude_code",
        scope="user",
    )


@pytest.mark.parametrize("mode", ["dry_run", "execute"])
def test_a_plan_that_writes_outside_the_root_is_refused(tmp_path, monkeypatch, mode):
    installer = _installer(tmp_path)
    elsewhere = tmp_path / "another-identity" / "settings.json"
    monkeypatch.setattr(installer, "plan", lambda: _plan_writing(elsewhere))
    with pytest.raises(RefusalError, match="writes outside"):
        installer.install(mode)
    assert not elsewhere.exists()


def test_writes_inside_the_root_and_the_home_are_allowed(tmp_path, monkeypatch):
    installer = _installer(tmp_path)
    inside = [installer.config_root / "settings.json", tmp_path / "ds-home" / "state" / "x"]
    for target in inside:
        monkeypatch.setattr(installer, "plan", lambda t=target: _plan_writing(t))
        installer._refuse_writes_outside_the_root(installer.plan())
