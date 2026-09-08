"""A completed update must clear the drift it just fixed.

WO 3e4ea639. Measured 2026-09-08: after `ds update` ran to completion, both projections of
``runtime/lib/enforcement.py`` were byte-identical to canonical -- verified at user scope
(``~/.claude/hooks/runtime/lib/enforcement.py``) and project scope -- and
``ds update --dry-run`` STILL reported the same file as drifted. The manifest at
``~/.dream-studio/integrations/claude_code/manifest.json`` had been rewritten by that run
(mtime matched to the minute) yet its entry still recorded the pre-update hash
``50fd7bb301e618bb`` against a canonical ``eb430a7e8b3d0a21``.

The manifest's ``content_hash`` is a CACHE of what was installed. It can go stale while the
installed file is correct -- and then the drift signal cannot be cleared by the command it
names, which is the unachievable-remedy shape this repo keeps finding: an operator who runs
the prescribed fix, succeeds, and is told again to run it learns to ignore the signal.

The installed file cannot go stale about itself, so it is the better witness. That is also
the comparison ``_check_hook_freshness`` already made, one check over.
"""

from __future__ import annotations

from pathlib import Path

from integrations.manifest import compute_hash
from interfaces.cli.commands.system_health import _canonical_hook_drift


def _tree(root: Path, *, canonical: str, installed: str | None) -> dict:
    """A canonical source tree plus an installed projection, and the manifest between them.

    Returns a manifest whose recorded hash is DELIBERATELY the pre-update value, which is
    the state the defect leaves behind.
    """
    (root / "runtime" / "lib").mkdir(parents=True, exist_ok=True)
    (root / "runtime" / "lib" / "enforcement.py").write_text(canonical, encoding="utf-8")

    installed_path = root / ".claude" / "hooks" / "runtime" / "lib" / "enforcement.py"
    if installed is not None:
        installed_path.parent.mkdir(parents=True, exist_ok=True)
        installed_path.write_text(installed, encoding="utf-8")

    return {
        "scope": "user",
        "files": [
            {
                "path": str(installed_path),
                "operation": "create",
                "content_hash": compute_hash("THE PRE-UPDATE SOURCE\n"),
            }
        ],
    }


def test_a_completed_update_reports_no_drift(tmp_path):
    """The symptom check for WO 3e4ea639.

    Canonical and the installed file agree; only the manifest's cached hash is stale. Before
    the fix this reported drift forever.
    """
    source = "AFTER = 1\n"
    manifest = _tree(tmp_path, canonical=source, installed=source)

    assert _canonical_hook_drift(tmp_path, manifest) == [], (
        "drift is reported although the installed file already matches canonical -- the"
        " stale manifest hash is being trusted over the file, so the update cannot clear"
        " its own signal"
    )


def test_a_genuinely_stale_installed_file_is_still_drift(tmp_path):
    """The control. Without it the fix above would pass equally against a check that
    reports clean unconditionally, which is worse than the defect."""
    manifest = _tree(tmp_path, canonical="AFTER = 1\n", installed="BEFORE = 1\n")

    assert _canonical_hook_drift(tmp_path, manifest) == ["lib/enforcement.py"]


def test_a_deleted_installed_file_is_drift(tmp_path):
    """Recorded as installed and now absent. This is the operator's original reported
    symptom -- an install that "didn't have some of the files needed"."""
    manifest = _tree(tmp_path, canonical="AFTER = 1\n", installed=None)

    assert _canonical_hook_drift(tmp_path, manifest) == ["lib/enforcement.py"]


def test_a_file_never_recorded_is_not_this_checks_business(tmp_path):
    """_canonical_skill_drift owns never-installed files; reporting them here would double
    every finding."""
    (tmp_path / "runtime" / "lib").mkdir(parents=True)
    (tmp_path / "runtime" / "lib" / "enforcement.py").write_text("X = 1\n", encoding="utf-8")

    assert _canonical_hook_drift(tmp_path, {"scope": "user", "files": []}) == []


def test_an_unreadable_installed_file_falls_back_to_the_cached_hash(tmp_path):
    """When the file cannot be read there is no better witness, and reporting clean on no
    evidence is the fail-open shape. The cached hash is stale-prone but it is evidence."""
    manifest = _tree(tmp_path, canonical="AFTER = 1\n", installed="AFTER = 1\n")
    # Point the manifest at a DIRECTORY: is_file() is False and no path was really removed,
    # so the fallback path is what runs.
    broken = tmp_path / ".claude" / "hooks" / "runtime" / "lib" / "a_directory.py"
    broken.mkdir(parents=True, exist_ok=True)
    manifest["files"] = [
        {
            "path": str(broken),
            "operation": "create",
            "content_hash": compute_hash("THE PRE-UPDATE SOURCE\n"),
        }
    ]
    # The name no longer matches enforcement.py, so nothing is compared -- which is the
    # never-recorded case, not a silent pass about enforcement.py.
    assert _canonical_hook_drift(tmp_path, manifest) == []


def test_the_check_reads_the_file_not_only_the_manifest():
    """Pins the mechanism, so a refactor cannot quietly return to trusting the cache.

    Asserted on the source because the behavioural cases above cannot distinguish "read the
    file" from "the cache happened to be right".
    """
    from pathlib import Path as _Path

    source = (
        _Path(__file__).resolve().parents[2]
        / "interfaces"
        / "cli"
        / "commands"
        / "system_health.py"
    ).read_text(encoding="utf-8")
    assert "installed.is_file()" in source
    assert "installed_hash" in source
