"""WO-FILESDB-P3 S3b-2: milestone gate reads artifacts from the docstore.

The gate (queries.py existence checks + close.py content checks) now reads
design-audit/security-audit/harden-results/cwv-results via read_milestone_artifact:
docstore-first (files.db, name 'milestones/<id>/<file>'), disk-fallback during the
.planning->docstore transition.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.files import store
from core.milestones.artifacts import read_milestone_artifact
from core.milestones.close import _evaluate_milestone_artifacts


@pytest.fixture
def files_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "files.db"
    monkeypatch.setattr(store, "files_db_path", lambda: db)
    return db


# ── read_milestone_artifact ─────────────────────────────────────────────────


def test_reads_from_docstore(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-1"  # not on disk
    store.write_file("milestones/ms-1/design-audit.md", "Score: 4/5\n", "text/markdown", "planning")
    assert read_milestone_artifact(ms_dir, "design-audit.md") == "Score: 4/5\n"


def test_falls_back_to_disk(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-2"
    ms_dir.mkdir(parents=True)
    (ms_dir / "harden-results.md").write_text("PASSED\n", encoding="utf-8")
    # nothing in the docstore for ms-2 -> disk fallback
    assert read_milestone_artifact(ms_dir, "harden-results.md") == "PASSED\n"


def test_returns_none_when_absent(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-3"
    assert read_milestone_artifact(ms_dir, "design-audit.md") is None


def test_docstore_takes_precedence_over_disk(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-4"
    ms_dir.mkdir(parents=True)
    (ms_dir / "security-audit.md").write_text("DISK\n", encoding="utf-8")
    store.write_file("milestones/ms-4/security-audit.md", "DOCSTORE\n", "text/markdown", "planning")
    assert read_milestone_artifact(ms_dir, "security-audit.md") == "DOCSTORE\n"


# ── gate passes with docstore-only artifacts (no disk) ──────────────────────


def test_gate_passes_with_docstore_only_artifacts(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-gate"  # never created on disk
    store.write_file(
        "milestones/ms-gate/design-audit.md", "Score: 4/5\n", "text/markdown", "planning"
    )
    store.write_file(
        "milestones/ms-gate/security-audit.md", "all clear\n", "text/markdown", "planning"
    )
    store.write_file(
        "milestones/ms-gate/harden-results.md", "PASSED\n", "text/markdown", "planning"
    )

    assert _evaluate_milestone_artifacts(ms_dir, has_ui=False) == []


def test_gate_fails_when_docstore_artifact_missing(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-partial"
    store.write_file(
        "milestones/ms-partial/design-audit.md", "Score: 4/5\n", "text/markdown", "planning"
    )
    # security-audit + harden-results absent from both docstore and disk
    failures = _evaluate_milestone_artifacts(ms_dir, has_ui=False)
    assert any("Security audit required" in f for f in failures)
    assert any("Hardening check required" in f for f in failures)


def test_gate_flags_blocked_from_docstore(tmp_path: Path, files_db: Path):
    ms_dir = tmp_path / "milestones" / "ms-blocked"
    store.write_file(
        "milestones/ms-blocked/design-audit.md", "Score: 4/5\n", "text/markdown", "planning"
    )
    store.write_file(
        "milestones/ms-blocked/security-audit.md", "BLOCKED finding\n", "text/markdown", "planning"
    )
    store.write_file(
        "milestones/ms-blocked/harden-results.md", "PASSED\n", "text/markdown", "planning"
    )
    failures = _evaluate_milestone_artifacts(ms_dir, has_ui=False)
    assert any("BLOCKED" in f for f in failures)
