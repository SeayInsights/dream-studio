"""Native release-notes generator — CalVer versioning + conventional commits (R5 T3).

Dream Studio versions with CalVer (``YYYY.M.D`` in pyproject.toml), so the *version* is
the release date — it is not derived from commit types the way release-please derives
semver. What IS derived from conventional commits is the release *content*: this module
groups the conventional-commit subjects since the last release into a Keep-a-Changelog
section. Owned natively (no external release action), matching the build-native principle.

The ``release`` GitHub Actions workflow (workflow_dispatch) calls ``main`` to produce the
notes for a release PR. Pure ``render_release_notes`` is unit-tested without git.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CONVENTIONAL = re.compile(
    r"^(?P<type>feat|fix|perf|refactor|docs|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)

# Conventional type -> changelog heading, in render order. Types not listed
# (chore, test, ci, docs by default) are omitted from user-facing release notes.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("perf", "Performance"),
    ("refactor", "Refactors"),
    ("revert", "Reverts"),
    ("build", "Build"),
)


def parse_conventional(subject: str) -> dict[str, str | bool] | None:
    """Parse a conventional-commit subject into {type, scope, breaking, desc}, or None
    if it is not conventional."""
    match = _CONVENTIONAL.match(subject.strip())
    if not match:
        return None
    return {
        "type": match.group("type"),
        "scope": match.group("scope") or "",
        "breaking": bool(match.group("breaking")),
        "desc": match.group("desc").strip(),
    }


def render_release_notes(subjects: list[str], version: str, date: str) -> str:
    """Render a Keep-a-Changelog section for a CalVer ``version`` released on ``date``,
    grouping conventional-commit subjects by type. BREAKING changes are called out first;
    non-conventional and omitted-type commits do not appear."""
    parsed = [p for s in subjects if (p := parse_conventional(s))]
    breaking = [p for p in parsed if p["breaking"]]

    lines = [f"## [{version}] - {date}", ""]
    if breaking:
        lines.append("### ⚠ BREAKING CHANGES")
        for p in breaking:
            lines.append(f"- {_fmt(p)}")
        lines.append("")
    for type_key, heading in _SECTIONS:
        items = [p for p in parsed if p["type"] == type_key]
        if not items:
            continue
        lines.append(f"### {heading}")
        for p in items:
            lines.append(f"- {_fmt(p)}")
        lines.append("")
    if len(lines) == 2:  # header only — nothing user-facing
        lines.append("_No user-facing changes._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _fmt(parsed: dict[str, str | bool]) -> str:
    scope = f"**{parsed['scope']}:** " if parsed["scope"] else ""
    return f"{scope}{parsed['desc']}"


def prepend_changelog(notes: str, changelog_path: Path) -> None:
    """Insert ``notes`` as a new version section immediately after ``## [Unreleased]``
    (releases newest-first). If there is no Unreleased section, append after the file's
    header block."""
    text = changelog_path.read_text(encoding="utf-8")
    marker = "## [Unreleased]"
    idx = text.find(marker)
    if idx == -1:
        changelog_path.write_text(text.rstrip() + "\n\n" + notes, encoding="utf-8")
        return
    line_end = text.find("\n", idx)
    insert_at = len(text) if line_end == -1 else line_end + 1
    new = text[:insert_at] + "\n" + notes + text[insert_at:]
    changelog_path.write_text(new, encoding="utf-8")


def bump_pyproject_version(version: str, pyproject_path: Path) -> None:
    """Set the first ``version = "..."`` line in pyproject.toml to ``version`` (CalVer)."""
    text = pyproject_path.read_text(encoding="utf-8")
    new = re.sub(r'(?m)^(version\s*=\s*")[^"]+(")', rf"\g<1>{version}\g<2>", text, count=1)
    pyproject_path.write_text(new, encoding="utf-8")


def _commits_since(ref: str | None) -> list[str]:
    rng = f"{ref}..HEAD" if ref else "HEAD"
    try:
        result = subprocess.run(
            ["git", "log", "--format=%s", rng],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _last_release_tag() -> str | None:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
    except Exception:
        return None
    tag = result.stdout.strip()
    return tag if result.returncode == 0 and tag else None


def main(argv: list[str] | None = None) -> int:
    """Print the release notes for the commits since the last release tag.

    ``--version`` and ``--date`` are supplied by the release workflow (CalVer date). No
    ``Date.now`` here so the module stays deterministic/importable; the workflow injects
    the date.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="CalVer version, e.g. 2026.8.2")
    parser.add_argument("--date", required=True, help="Release date, YYYY-MM-DD")
    parser.add_argument("--since", default=None, help="Base ref (default: last release tag)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update CHANGELOG.md + pyproject.toml in place (default: print notes only)",
    )
    args = parser.parse_args(argv)

    since = args.since or _last_release_tag()
    notes = render_release_notes(_commits_since(since), args.version, args.date)
    if args.apply:
        prepend_changelog(notes, REPO_ROOT / "CHANGELOG.md")
        bump_pyproject_version(args.version, REPO_ROOT / "pyproject.toml")
        print(f"Applied release {args.version} to CHANGELOG.md + pyproject.toml")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
