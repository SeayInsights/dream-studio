"""Test-list completeness gate (WO-CI-COMPLETENESS).

The 2026-08-18 audit found the pre-push ``pin-tests`` list and the pr-smoke
focused-tests list are hardcoded file lists with no completeness check: a
listed file that is deleted or renamed silently stops guarding anything, and
new test files are silently never run pre-merge (the full suite runs
post-merge, ubuntu-only). This gate makes the lists self-checking:

- BLOCKING: every file named in the pin-tests manifest and the pr-smoke
  focused list must exist on disk. A vanished pin is a dead guard.
- ADVISORY: prints how many tests/unit files are NOT covered by any pre-merge
  list — silent truncation must at least be visible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_PUSH_MANIFEST = _REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_TEST_PATH = re.compile(r"(tests/[A-Za-z0-9_./-]+\.py)")


def listed_test_paths() -> dict[str, list[str]]:
    """Every test path named in the two pre-merge gate lists, by source."""
    sources: dict[str, list[str]] = {}
    for name, path in (("pre-push.yaml", _PRE_PUSH_MANIFEST), ("ci.yml", _CI_WORKFLOW)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            sources[name] = []
            continue
        sources[name] = sorted(set(_TEST_PATH.findall(text)))
    return sources


def missing_listed_files(sources: dict[str, list[str]] | None = None) -> list[tuple[str, str]]:
    """(source, path) pairs for listed test files that do not exist — dead guards."""
    sources = sources if sources is not None else listed_test_paths()
    missing: list[tuple[str, str]] = []
    for name, paths in sources.items():
        for rel in paths:
            if not (_REPO_ROOT / rel).is_file():
                missing.append((name, rel))
    return missing


def impact_relevant_unlisted(
    changed_files: list[str], sources: dict[str, list[str]] | None = None
) -> list[str]:
    """NAMED unlisted test files the current change set makes relevant.

    Gap WO e3e6b5a9 (from WO-CI-COMPLETENESS's own review): the advisory printed
    only a count — the blast_radius impact set now names the test files this
    push's changes depend on that no pre-merge list runs. Those are the tests
    most likely to break post-merge, invisible until full-ci.
    """
    from core.gates.blast_radius import compute_impact_set

    sources = sources if sources is not None else listed_test_paths()
    listed = {p for paths in sources.values() for p in paths}
    dependent = compute_impact_set(changed_files, repo_root=_REPO_ROOT)["dependent_tests"]
    return sorted(t for t in dependent if t not in listed and t.startswith("tests/"))


def _changed_files() -> list[str]:
    """Changed files for the push (base ref envs mirror the sibling gates)."""
    import os
    import subprocess

    base_ref = os.environ.get("DREAM_STUDIO_BASE_REF", "origin/main")
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def unlisted_unit_files(sources: dict[str, list[str]] | None = None) -> list[str]:
    """tests/unit files no pre-merge list runs (advisory — they first run
    post-merge in full-ci, ubuntu-only)."""
    sources = sources if sources is not None else listed_test_paths()
    listed = {p for paths in sources.values() for p in paths}
    unit_dir = _REPO_ROOT / "tests" / "unit"
    if not unit_dir.is_dir():
        return []
    all_unit = {
        f.relative_to(_REPO_ROOT).as_posix()
        for f in unit_dir.rglob("test_*.py")
        if "__pycache__" not in f.parts
    }
    return sorted(all_unit - listed)


def main() -> int:
    sources = listed_test_paths()
    missing = missing_listed_files(sources)
    if missing:
        print("TEST-LIST COMPLETENESS: listed test file(s) no longer exist — dead guards:")
        for name, rel in missing:
            print(f"  [{name}] {rel}")
        print("Remove or repoint the entry in the SAME change set as the rename/delete.")
        return 1

    unlisted = unlisted_unit_files(sources)
    total_listed = sum(len(v) for v in sources.values())
    print(
        f"test-list completeness: {total_listed} listed path(s) all present; "
        f"{len(unlisted)} tests/unit file(s) run only post-merge (full-ci, ubuntu-only)."
    )

    # Advisory (named, blast_radius-derived): tests THIS push's changes depend on
    # that no pre-merge list runs — the likeliest post-merge reds.
    relevant = impact_relevant_unlisted(_changed_files(), sources)
    if relevant:
        print(
            f"ADVISORY: {len(relevant)} impact-relevant test file(s) run only post-merge"
            " for this change set:"
        )
        for rel in relevant[:20]:
            print(f"  {rel}")
        if len(relevant) > 20:
            print(f"  ...and {len(relevant) - 20} more.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
