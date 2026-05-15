from __future__ import annotations

from pathlib import Path

from core.release.adapter_workspace_hygiene import (
    adapter_workspace_policy,
    classify_adapter_workspace_path,
    ensure_local_git_excludes,
    required_local_exclude_patterns,
)
from interfaces.cli import setup


def test_active_adapter_surfaces_and_projections_remain_repo_tracked() -> None:
    agents = classify_adapter_workspace_path("AGENTS.md")
    claude = classify_adapter_workspace_path("CLAUDE.md")
    projection = classify_adapter_workspace_path("adapter-projections/codex/AGENTS.md")

    assert agents["category"] == "active_adapter_projection"
    assert claude["category"] == "active_adapter_projection"
    assert projection["category"] == "generated_adapter_projection"
    assert agents["repo_tracked"] is True
    assert claude["repo_tracked"] is True
    assert projection["repo_tracked"] is True
    assert projection["generated_projection"] is True
    assert agents["local_exclude_required"] is False


def test_adapter_scratch_paths_are_local_exclude_only() -> None:
    worktree = classify_adapter_workspace_path(".claude/worktrees/session-1/AGENTS.md")
    codex_session = classify_adapter_workspace_path(".codex/sessions/2026/rollout.jsonl")
    scratch = classify_adapter_workspace_path(".adapter-scratch/tmp.json")

    for item in (worktree, codex_session, scratch):
        assert item["category"] == "local_adapter_scratch"
        assert item["repo_tracked"] is False
        assert item["local_exclude_required"] is True
        assert item["content_inspection_required"] is False


def test_unknown_or_sensitive_adapter_files_require_classification_not_cleanup() -> None:
    unknown = classify_adapter_workspace_path(".windsurf/local-state.json")
    sensitive = classify_adapter_workspace_path(".codex/auth-token.json")

    assert unknown["category"] == "unknown_adapter_file"
    assert unknown["requires_manual_review"] is True
    assert sensitive["category"] == "sensitive_manual_review"
    assert sensitive["requires_manual_review"] is True
    assert sensitive["content_inspection_required"] is False


def test_local_git_excludes_are_precise_and_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text("# local excludes\n.claude/worktrees/\n", encoding="utf-8")

    first = ensure_local_git_excludes(repo)
    second = ensure_local_git_excludes(repo)
    text = exclude.read_text(encoding="utf-8")

    assert ".claude/worktrees/" in text
    assert ".codex/sessions/" in text
    assert first["changed"] is True
    assert second["changed"] is False
    assert text.count(".claude/worktrees/") == 1


def test_setup_check_reports_local_excludes_without_writing(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(setup, "REPO_ROOT", repo)

    report = setup._local_adapter_exclude_report()

    assert report["available"] is True
    assert report["local_only"] is True
    assert set(report["missing_patterns"]) == set(required_local_exclude_patterns())
    assert not (repo / ".git" / "info" / "exclude").exists()


def test_policy_does_not_use_repo_gitignore_for_machine_specific_scratch() -> None:
    policy = adapter_workspace_policy()

    assert ".claude/worktrees/" in policy["local_exclude_patterns"]
    assert "AGENTS.md" in policy["repo_tracked"]
    assert "CLAUDE.md" in policy["repo_tracked"]
    assert "adapter-projections/*" in policy["repo_tracked"]
    assert policy["live_db_mutation_authorized"] is False
