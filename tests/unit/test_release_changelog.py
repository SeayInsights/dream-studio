"""R5 T3 — native CalVer release-notes generator.

Changelog content is derived from conventional commits; the version stays CalVer (the
release date). See core/release/changelog.py.
"""

from __future__ import annotations

from pathlib import Path

from core.release.changelog import (
    bump_pyproject_version,
    parse_conventional,
    prepend_changelog,
    render_release_notes,
)


def test_parse_conventional():
    p = parse_conventional("feat(gates): add the thing")
    assert p == {"type": "feat", "scope": "gates", "breaking": False, "desc": "add the thing"}
    assert parse_conventional("fix: typo")["type"] == "fix"
    assert parse_conventional("feat(api)!: drop v1")["breaking"] is True
    assert parse_conventional("not a conventional commit") is None


def test_render_release_notes_groups_by_type_and_flags_breaking():
    subjects = [
        "feat(gates): ratified-contract gate",
        "fix(analytics): read path must not fabricate",
        "feat(api)!: remove the v1 endpoint",
        "chore: bump deps",  # omitted from user-facing notes
        "docs: tidy readme",  # omitted
        "not conventional at all",  # ignored
    ]
    notes = render_release_notes(subjects, "2026.8.2", "2026-08-02")

    assert notes.startswith("## [2026.8.2] - 2026-08-02")
    assert "### ⚠ BREAKING CHANGES" in notes
    assert "- **api:** remove the v1 endpoint" in notes
    assert "### Features" in notes and "- **gates:** ratified-contract gate" in notes
    assert "### Fixes" in notes and "- **analytics:** read path must not fabricate" in notes
    # chore/docs/non-conventional do not appear.
    assert (
        "bump deps" not in notes and "tidy readme" not in notes and "not conventional" not in notes
    )


def test_render_release_notes_empty_when_no_user_facing_changes():
    notes = render_release_notes(["chore: x", "ci: y"], "2026.8.2", "2026-08-02")
    assert "_No user-facing changes._" in notes


def test_prepend_changelog_inserts_after_unreleased(tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [2026.5.17] - 2026-05-17\n\n### Features\n- old\n",
        encoding="utf-8",
    )
    prepend_changelog("## [2026.8.2] - 2026-08-02\n\n### Fixes\n- new\n", cl)
    text = cl.read_text(encoding="utf-8")
    # The new section lands after [Unreleased] and before the older release.
    assert text.index("[2026.8.2]") < text.index("[2026.5.17]")
    assert text.index("## [Unreleased]") < text.index("[2026.8.2]")


def test_bump_pyproject_version(tmp_path: Path):
    pp = tmp_path / "pyproject.toml"
    pp.write_text('[project]\nname = "x"\nversion = "2026.5.17"\n', encoding="utf-8")
    bump_pyproject_version("2026.8.2", pp)
    assert 'version = "2026.8.2"' in pp.read_text(encoding="utf-8")
