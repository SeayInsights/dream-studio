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


def test_changelog_has_versioned_release_entry() -> None:
    """WO-REL-DOCS T2: CHANGELOG must carry a versioned semver release entry (not only
    [Unreleased]) matching the current VERSION, so every release is documented."""
    import re

    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    entries = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}", changelog, re.M)
    assert entries, "CHANGELOG must have a versioned release entry '## [X.Y.Z] - YYYY-MM-DD'"
    assert (
        version in entries
    ), f"CHANGELOG must document the current VERSION {version!r}; found release entries {entries}"


def test_readme_covers_marketplace_install_and_uninstall() -> None:
    """WO-REL-DOCS T1: the README must document the public plugin path — marketplace install,
    first-run runtime setup, and uninstall — for public plugin users."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "/plugin marketplace add" in readme, "README must document the marketplace install"
    assert "seayinsights/dream-studio" in readme, "README must reference the public repo"
    assert "ds uninstall" in readme, "README must document how to uninstall"
    # No stale reference to the non-public dev repo name.
    assert "dream-studio-clean" not in readme, "README must not reference the non-public repo name"


def test_user_facing_docs_use_public_repo_name() -> None:
    """WO-REL-DOCS-UNIFY (8726d174): the docs public users read (README + docs/**/*.md) must
    reference the public repo name, never the local dev dir name 'dream-studio-clean'.

    Scope is deliberately the LIVING user-facing doc surface. Excluded: dated audit archives
    under docs/audits/ (historical snapshots of a past state, like the CHANGELOG), and
    functional code/config/test refs to the local working directory (which really is named
    dream-studio-clean) — those are a separate, non-cosmetic concern a blanket rename would break.
    """
    surfaces = [REPO_ROOT / "README.md"]
    surfaces += [
        p
        for p in (REPO_ROOT / "docs").rglob("*.md")
        if "audits" not in p.relative_to(REPO_ROOT / "docs").parts
    ]
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in surfaces
        if p.is_file() and "dream-studio-clean" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"living user-facing docs must use the public repo name: {offenders}"


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
