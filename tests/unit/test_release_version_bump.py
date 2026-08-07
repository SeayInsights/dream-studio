"""WO 18bcaea6: the release flow bumps semver VERSION + pyproject and regenerates the
manifests — no CalVer path survives.

Spawned by the WO-REL-PACKAGING review: WO-REL-PACKAGING switched VERSION to semver but the
release automation still computed a CalVer date and never wrote VERSION or regenerated the
manifests. These guards lock the wired-up semver release flow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.release.changelog import SEMVER_RE, bump_version_file, main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bump_version_file_writes_semver(tmp_path: Path) -> None:
    """--apply writes the chosen semver to the VERSION file (single source of truth)."""
    vf = tmp_path / "VERSION"
    vf.write_text("0.1.0\n", encoding="utf-8")
    bump_version_file("0.2.0", vf)
    assert vf.read_text(encoding="utf-8").strip() == "0.2.0"
    assert SEMVER_RE.match(vf.read_text(encoding="utf-8").strip())


def test_release_rejects_non_semver_version() -> None:
    """A dashed CalVer date (the pre-fix default shape) is rejected before any file write."""
    with pytest.raises(SystemExit):
        main(["--apply", "--version", "2026-08-07", "--date", "2026-08-07"])


def test_release_path_makes_no_calver_claim() -> None:
    """No file in the release path still claims Dream Studio versions with CalVer."""
    changelog = (REPO_ROOT / "core" / "release" / "changelog.py").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "CalVer" not in changelog, "changelog.py must not claim CalVer versioning"
    assert "CalVer" not in workflow, "release.yml must not claim CalVer versioning"
    # The workflow must drive the semver bump through --apply (VERSION + manifests).
    assert "--apply" in workflow


def test_readiness_doc_describes_automated_bump() -> None:
    """The Versioning section documents the automated release-flow bump, not a manual regen."""
    doc = (REPO_ROOT / "docs" / "operations" / "public-release-readiness.md").read_text(
        encoding="utf-8"
    )
    assert "`release` workflow" in doc
    assert "changelog.py --apply" in doc
