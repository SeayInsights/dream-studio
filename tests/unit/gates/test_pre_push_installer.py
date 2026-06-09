"""B.3 — Installer wiring for the git pre-push hook.

Verifies that ClaudeCodeInstaller.plan() includes a FileOp for the pre-push
hook only when `git_repo_root` is explicitly provided AND that directory
contains a `.git/hooks/` subtree. Tests are hermetic — they never touch the
operator's real .git/hooks/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.installer.claude_code import ClaudeCodeInstaller  # noqa: E402


@pytest.fixture
def config_root(tmp_path: Path) -> Path:
    target = tmp_path / "claude_config"
    target.mkdir()
    return target


@pytest.fixture
def ds_home(tmp_path: Path) -> Path:
    target = tmp_path / "dream_studio_home"
    target.mkdir()
    return target


def _fake_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake_repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    return repo


def test_plan_omits_git_hook_when_no_git_repo_root(config_root, ds_home):
    """Default behavior: no `git_repo_root` → no pre-push FileOp."""
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=ds_home,
    )
    plan = installer.plan()
    targets = [str(op.target) for op in plan.ops]
    assert not any(t.endswith(str(Path(".git") / "hooks" / "pre-push")) for t in targets)


def test_plan_includes_git_hook_when_git_repo_root_provided(config_root, ds_home, tmp_path):
    """With `git_repo_root` pointing at a fake repo, the hook FileOp is planned."""
    repo = _fake_git_repo(tmp_path)
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=ds_home,
        git_repo_root=repo,
    )
    plan = installer.plan()
    hook_target = repo / ".git" / "hooks" / "pre-push"
    matching = [op for op in plan.ops if op.target == hook_target]
    assert (
        matching
    ), f"Expected pre-push FileOp at {hook_target}; targets were {[op.target for op in plan.ops]}"
    op = matching[0]
    assert op.source_content is not None
    assert "ds workflow run pre-push" in op.source_content


def test_install_writes_git_hook_to_fake_repo(config_root, ds_home, tmp_path):
    """Executing the install writes the pre-push hook into the fake repo."""
    repo = _fake_git_repo(tmp_path)
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=ds_home,
        git_repo_root=repo,
    )
    installer.install("execute")
    hook = repo / ".git" / "hooks" / "pre-push"
    assert hook.is_file(), "pre-push hook was not installed"
    content = hook.read_text(encoding="utf-8")
    assert "ds workflow run pre-push --non-interactive" in content


def test_plan_omits_git_hook_when_dot_git_missing(config_root, ds_home, tmp_path):
    """If the supplied `git_repo_root` has no .git/hooks/, the FileOp is skipped."""
    repo = tmp_path / "not_a_repo"
    repo.mkdir()
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=REPO_ROOT / "canonical",
        ds_home=ds_home,
        git_repo_root=repo,
    )
    plan = installer.plan()
    assert not any(op.target == repo / ".git" / "hooks" / "pre-push" for op in plan.ops)
