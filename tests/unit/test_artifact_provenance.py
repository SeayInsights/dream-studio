"""WO-VERIFY-PROVENANCE: provenance envelopes on gate-consumed artifacts.

Covers the four blind spots the 2026-08-18 enforcement audit found in the
artifact gates: hand-written verdicts passed ``json.loads`` with no provenance
check, verdicts were not tied to any commit, artifact gates accepted stale
files, and re-running verify until green left no trace of what was graded.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from core.config.sqlite_bootstrap import bootstrap_database
from core.work_orders.artifact_envelope import git_head_sha, unwrap, wrap
from core.work_orders.artifacts import (
    get_wo_artifact,
    get_wo_artifact_envelope,
    set_wo_artifact,
)
from core.work_orders.close_gates import run_gate_check
from core.work_orders.verify_persist import _persist_review_verdict

PROJECT_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
WO_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NOW = "2026-08-18T00:00:00+00:00"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one initial commit (the graded state)."""
    repo = tmp_path / "target-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.local")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("one", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", f"initial work ({WO_ID[:8]})")
    return repo


@pytest.fixture
def db(tmp_path, repo):
    """Authority DB with one project (project_path -> repo) and one WO."""
    db_path = tmp_path / "state" / "studio.db"
    db_path.parent.mkdir(parents=True)
    bootstrap_database(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO business_projects (project_id, name, description, status,"
            " project_path, created_at, updated_at)"
            " VALUES (?, 'Test Project', 'desc', 'active', ?, ?, ?)",
            (PROJECT_ID, str(repo), NOW, NOW),
        )
        conn.execute(
            "INSERT INTO business_work_orders"
            " (work_order_id, project_id, milestone_id, title, description, status,"
            " work_order_type, created_at, updated_at)"
            " VALUES (?, ?, NULL, 'WO-PROV-TEST', NULL, 'in_progress',"
            " 'infrastructure', ?, ?)",
            (WO_ID, PROJECT_ID, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _wo_commit(repo: Path, message: str) -> None:
    marker = repo / "b.txt"
    marker.write_text(message, encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", message)


def _gate(db_path: Path, tmp_path: Path, gate: str) -> tuple[bool, str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return run_gate_check(
            gate,
            planning_root=tmp_path / ".planning",
            work_order_id=WO_ID,
            project_id=PROJECT_ID,
            conn=conn,
            db_path=db_path,
        )
    finally:
        conn.close()


# ── envelope primitives ─────────────────────────────────────────────────────────


def test_wrap_unwrap_roundtrip(repo):
    sha = git_head_sha(repo)
    stored = wrap("artifact body", generator="ds work-order verify", head_commit_sha=sha)
    content, envelope = unwrap(stored)
    assert content == "artifact body"
    assert envelope is not None
    assert envelope["generator"] == "ds work-order verify"
    assert envelope["head_commit_sha"] == sha
    assert envelope["created_at"]


def test_unwrap_legacy_text_and_plain_json():
    assert unwrap("bare markdown text") == ("bare markdown text", None)
    plain = json.dumps({"passed": True})
    assert unwrap(plain) == (plain, None)
    assert unwrap(None) == (None, None)


def test_set_artifact_with_generator_records_envelope(db, repo):
    ok = set_wo_artifact(
        WO_ID,
        "security_scan",
        "No BLOCKED findings",
        db_path=db,
        generator="ds-quality security",
        project_root=repo,
    )
    assert ok is True
    # Transparent read returns the bare content...
    assert get_wo_artifact(WO_ID, "security_scan", db_path=db) == "No BLOCKED findings"
    # ...and the envelope carries the repo HEAD at write time.
    content, envelope = get_wo_artifact_envelope(WO_ID, "security_scan", db_path=db)
    assert content == "No BLOCKED findings"
    assert envelope is not None
    assert envelope["head_commit_sha"] == git_head_sha(repo)


# ── independent_review gate: provenance required ───────────────────────────────


def test_handwritten_verdict_rejected(db, repo, tmp_path):
    """A hand-written {"passed": true} must not satisfy the gate (audit finding:
    close_gates did bare json.loads with zero provenance validation)."""
    set_wo_artifact(WO_ID, "review_verdict", json.dumps({"passed": True}), db_path=db)
    passed, reason = _gate(db, tmp_path, "independent_review")
    assert passed is False
    assert "provenance" in reason
    assert "work-order verify" in reason


def test_stale_verdict_blocks_close(db, repo, tmp_path):
    """A verdict graded at HEAD^ is stale once a newer WO commit lands."""
    _persist_review_verdict(
        WO_ID,
        {"work_order_id": WO_ID, "passed": True, "graded_commits": []},
        planning_root=tmp_path / ".planning",
        db_path=db,
        project_root=repo,
    )
    # Fresh verdict, no commits after it: gate passes.
    passed, reason = _gate(db, tmp_path, "independent_review")
    assert passed is True, reason

    # A WO-attributed commit lands after the verdict was produced: stale.
    _wo_commit(repo, f"follow-up change ({WO_ID[:8]})")
    passed, reason = _gate(db, tmp_path, "independent_review")
    assert passed is False
    assert "stale" in reason


def test_unrelated_commit_does_not_stale_verdict(db, repo, tmp_path):
    """Staleness is WO-scoped: commits not referencing the WO leave it fresh."""
    _persist_review_verdict(
        WO_ID,
        {"work_order_id": WO_ID, "passed": True},
        planning_root=tmp_path / ".planning",
        db_path=db,
        project_root=repo,
    )
    _wo_commit(repo, "unrelated maintenance commit")
    passed, reason = _gate(db, tmp_path, "independent_review")
    assert passed is True, reason


# ── artifact gates: enveloped artifacts must be fresh ──────────────────────────


def test_stale_security_scan_blocks_close(db, repo, tmp_path):
    set_wo_artifact(
        WO_ID,
        "security_scan",
        "No BLOCKED findings",
        db_path=db,
        generator="ds-quality security",
        project_root=repo,
    )
    # Fresh: passes.
    passed, reason = _gate(db, tmp_path, "security_scan")
    assert passed is True, reason

    _wo_commit(repo, f"more work after the scan ({WO_ID[:8]})")
    passed, reason = _gate(db, tmp_path, "security_scan")
    assert passed is False
    assert "stale" in reason


def test_legacy_security_scan_still_accepted(db, repo, tmp_path):
    """Envelope-less (legacy) artifacts keep their historical acceptance."""
    set_wo_artifact(WO_ID, "security_scan", "No BLOCKED findings", db_path=db)
    _wo_commit(repo, f"more work after the scan ({WO_ID[:8]})")
    passed, reason = _gate(db, tmp_path, "security_scan")
    assert passed is True, reason


# ── whole-repo staleness + milestone audit gates (gap WO 1c49e8ca) ─────────────


def test_commits_after_whole_repo_staleness(repo):
    """commits_after: ANY commit after the sha counts — the milestone-audit signal."""
    from core.work_orders.artifact_envelope import commits_after

    sha = git_head_sha(repo)
    assert commits_after(sha, repo) == []
    # An unrelated commit (no WO reference) IS whole-repo staleness.
    _wo_commit(repo, "unrelated maintenance commit")
    newer = commits_after(sha, repo)
    assert newer == [git_head_sha(repo)]
    # Unanswerable cases return None, never a false verdict.
    assert commits_after("0" * 40, repo) is None
    assert commits_after(sha, None) is None
    assert commits_after(sha, repo / "not-a-dir") is None


def test_read_milestone_artifact_with_envelope(tmp_path, repo):
    """Enveloped disk artifacts return their metadata; legacy files return None."""
    from core.milestones.artifacts import (
        read_milestone_artifact,
        read_milestone_artifact_with_envelope,
    )

    ms_dir = tmp_path / "ms-prov-test-0001"
    ms_dir.mkdir()
    sha = git_head_sha(repo)
    (ms_dir / "harden-results.md").write_text(
        wrap("All checks PASSED", generator="ds-quality harden", head_commit_sha=sha),
        encoding="utf-8",
    )
    (ms_dir / "security-audit.md").write_text("No BLOCKED findings", encoding="utf-8")

    content, envelope = read_milestone_artifact_with_envelope(ms_dir, "harden-results.md")
    assert content == "All checks PASSED"
    assert envelope is not None and envelope["head_commit_sha"] == sha
    # Transparent reader unwraps; legacy file carries no envelope.
    assert read_milestone_artifact(ms_dir, "harden-results.md") == "All checks PASSED"
    assert read_milestone_artifact_with_envelope(ms_dir, "security-audit.md") == (
        "No BLOCKED findings",
        None,
    )
    assert read_milestone_artifact_with_envelope(ms_dir, "absent.md") == (None, None)


def test_milestone_stale_audit_rejected(tmp_path, repo):
    """An enveloped milestone audit predating ANY later commit fails the gate;
    fresh enveloped and legacy artifacts pass (the untested reject path from
    _evaluate_milestone_artifacts, gap WO 1c49e8ca)."""
    from core.milestones.close import _evaluate_milestone_artifacts

    ms_dir = tmp_path / "ms-prov-test-0002"
    ms_dir.mkdir()
    sha = git_head_sha(repo)
    (ms_dir / "security-audit.md").write_text(
        wrap("No BLOCKED findings", generator="ds-quality security", head_commit_sha=sha),
        encoding="utf-8",
    )
    (ms_dir / "harden-results.md").write_text("PASSED", encoding="utf-8")  # legacy

    # Fresh enveloped audit + legacy hardening: no failures.
    failures = _evaluate_milestone_artifacts(ms_dir, has_ui=False, project_root=repo)
    assert failures == [], failures

    # Any later commit stales the enveloped audit — legacy stays accepted.
    _wo_commit(repo, "unrelated post-audit commit")
    failures = _evaluate_milestone_artifacts(ms_dir, has_ui=False, project_root=repo)
    assert any("security-audit.md is stale" in f for f in failures), failures
    assert not any("harden-results" in f for f in failures), failures
