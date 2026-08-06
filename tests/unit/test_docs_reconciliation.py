"""Docs reconciliation guards.

- WO c64dd3db (from WO-FILESDB-REVET task 3): the retain-or-drop verdict for
  business_work_order_artifacts must stay documented in aspirational-schema-debt.md
  (authority-vs-disk necessity + review_verdict-vs-verify_* overlap).
- WO-DOC-RESIDUE (692fe0d5): docs/token-overhead.md is internal methodology and must
  stay untracked per the push principle (its sibling was already removed).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_public_release_readiness_doc_lists_blockers() -> None:
    """WO-REL-CI-BASELINE T2: the release-readiness doc exists and lists every release
    blocker, so the ship gate has a single checklist to consult."""
    doc = REPO_ROOT / "docs" / "operations" / "public-release-readiness.md"
    assert doc.is_file(), "docs/operations/public-release-readiness.md must exist"
    text = doc.read_text(encoding="utf-8").lower()
    for blocker in ("full-ci", "publication boundary", "packaging", "ship-closeout", "go/no-go"):
        assert blocker in text, f"release-readiness doc missing blocker: {blocker}"
    assert "ship gate" in text, "doc must reference the ship gate that consults it"


def test_artifacts_keep_verdict_documented() -> None:
    text = (REPO_ROOT / "docs" / "architecture" / "aspirational-schema-debt.md").read_text(
        encoding="utf-8"
    )
    assert "Retain-or-drop verdict" in text
    # Both required verdict points are recorded.
    assert "business_work_order_artifacts" in text
    assert "review_verdict" in text and "verify_status" in text
    # The keep decision (not a drop) is explicit.
    assert "Verdict: KEEP" in text


def test_token_overhead_doc_untracked_per_push_principle() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "docs/token-overhead.md" in gitignore, (
        "docs/token-overhead.md must be gitignored (internal methodology, "
        "untracked per the push principle — WO-DOC-RESIDUE)"
    )
