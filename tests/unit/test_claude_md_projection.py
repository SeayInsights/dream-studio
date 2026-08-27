"""WO-CLAUDEMD-CLOBBER: a generated projection must not destroy hand-written content.

MEASURED 2026-08-21:

    CLAUDE.md                            205 lines   BEGIN sentinels=0  END=0
    .claude/CLAUDE.md                    101 lines   BEGIN=1  END=1
    ~/.claude/CLAUDE.md                  101 lines   BEGIN=1  END=1
    adapter-projections/claude/CLAUDE.md  35 lines   BEGIN=1  END=1

The two 101-line files were FULL GENERATED COPIES written by the installer.
``~/.claude/CLAUDE.md`` is the operator's GLOBAL personal instruction file for every
project, and it was an install target with no protected region: anything hand-written
there was destroyed by ``ds integrate install`` or ``ds doctor --fix``. Operator report:
"when it builds it rewrites all of claude.md."

THE CORRECT MECHANISM ALREADY EXISTED AND THE INSTALLER BYPASSED IT.
``interfaces/cli/generate_routing.py::update_claude_md`` replaces only the span between
the two markers and REFUSES a file that has neither. The installer emitted
``op="create"`` carrying the whole generated file, and the apply loop atomic_writes
anything with ``source_content``.

WHY THESE TESTS DRIVE THE INSTALLER AND NOT JUST THE HELPER. A test of
``merge_claude_md`` alone would pass with the installer still bypassing it -- which is
the defect, not the fix. The helper is unit-tested here too, but the property that was
violated is asserted through ``ClaudeCodeInstaller.install("execute")``, the path the
operator actually runs.

AND IT ASSERTS THE CONTENT OUTSIDE, BYTE FOR BYTE. Asserting only that the generated
region was updated would not have caught this: the old writer updated that region
correctly. It also destroyed everything around it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.compiler.claude_code import (
    CLAUDE_MD_CREATED,
    CLAUDE_MD_REFUSED,
    CLAUDE_MD_SPLICED,
    CLAUDE_MD_UNCHANGED,
    merge_claude_md,
)
from integrations.installer.claude_code import ClaudeCodeInstaller
from integrations.manifest import get_manifest_path

BEGIN = "<!-- BEGIN AUTO-ROUTING -->"
END = "<!-- END AUTO-ROUTING -->"

ABOVE = """# MY OWN GLOBAL INSTRUCTIONS

- Never push directly to main.
- My personal note that no generator has any business touching.
"""

BELOW = """
## My own trailing section

Another hand-written paragraph, below the generated region.
"""


def _marked(body: str = "old generated body") -> str:
    return f"{ABOVE}\n{BEGIN}\n{body}\n{END}\n{BELOW}"


@pytest.fixture
def config_root(tmp_path: Path) -> Path:
    root = tmp_path / "dot_claude"
    root.mkdir()
    return root


@pytest.fixture
def canonical_root(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    skill_dir = root / "skills" / "ds-bootstrap"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# ds-bootstrap\nWhen Dream Studio is installed, prefer applicable DS skills.",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def ds_home(tmp_path: Path) -> Path:
    home = tmp_path / "ds_home"
    home.mkdir()
    return home


def _install(config_root: Path, canonical_root: Path, ds_home: Path) -> dict:
    installer = ClaudeCodeInstaller(
        config_root,
        "user",
        canonical_root=canonical_root,
        ds_home=ds_home,
        skip_hook_install=True,
    )
    return installer.install("execute")


# -- The property that was violated -------------------------------------------


def test_hand_written_content_outside_the_sentinels_survives_a_write(
    config_root, canonical_root, ds_home
):
    """THE DEFECT, THROUGH THE OPERATOR'S OWN PATH.

    Byte-for-byte on both sides. The old writer replaced the whole file, so ABOVE and
    BELOW were gone; asserting only that the generated region changed would have passed
    against the broken writer.
    """
    target = config_root / "CLAUDE.md"
    target.write_text(_marked(), encoding="utf-8")

    _install(config_root, canonical_root, ds_home)

    after = target.read_text(encoding="utf-8")
    assert after.startswith(ABOVE), "hand-written content ABOVE the markers was destroyed"
    assert after.endswith(BELOW), "hand-written content BELOW the markers was destroyed"
    assert "My personal note that no generator has any business touching." in after
    assert "Another hand-written paragraph, below the generated region." in after
    assert after.count(BEGIN) == 1, "the markers must not be duplicated"
    assert after.count(END) == 1


def test_a_file_with_no_markers_is_left_completely_untouched(config_root, canonical_root, ds_home):
    """The repo-root CLAUDE.md is 205 lines with no markers. It survived only because a
    DIFFERENT code path happened to refuse it -- an accident of routing, not a rule.

    A hand-written file is not a projection, and this writer must refuse rather than
    guess where the boundary is.
    """
    target = config_root / "CLAUDE.md"
    original = "# Entirely hand written\n\nNo markers anywhere in this file.\n"
    target.write_text(original, encoding="utf-8")

    result = _install(config_root, canonical_root, ds_home)

    assert target.read_text(encoding="utf-8") == original, "an unmarked file was overwritten"
    written = [f["path"] for f in result["files_written"]]
    assert str(target) not in written, "the refused file must not be reported as written"

    skipped = [op for op in result["plan"] if op["target"] == str(target)]
    assert skipped and skipped[0]["op"] == "skip", "the refusal must be visible in the plan"


def test_the_refusal_says_what_to_do_about_it(config_root, canonical_root, ds_home):
    """A silent skip is its own failure: the operator would not know their routing block
    was never installed. The reason has to name the fix."""
    target = config_root / "CLAUDE.md"
    target.write_text("# Hand written, unmarked\n", encoding="utf-8")

    result = _install(config_root, canonical_root, ds_home)
    reasons = [op.get("reason", "") for op in result["plan"] if op["target"] == str(target)]
    assert reasons, "the skipped op must appear in the plan"
    reason = reasons[0]
    assert "no generated region" in reason
    assert BEGIN in reason and END in reason, "name the markers the operator must add"


def test_the_generated_region_is_actually_updated(config_root, canonical_root, ds_home):
    """The converse of the preservation test. Refusing to clobber must not become
    refusing to do the job -- a writer that preserves everything by writing nothing
    would pass every test above."""
    target = config_root / "CLAUDE.md"
    target.write_text(_marked(body="STALE CONTENT THAT MUST BE REPLACED"), encoding="utf-8")

    _install(config_root, canonical_root, ds_home)

    after = target.read_text(encoding="utf-8")
    assert "STALE CONTENT THAT MUST BE REPLACED" not in after, "the region was not updated"
    begin_at = after.find(BEGIN)
    end_at = after.find(END)
    assert begin_at < end_at
    region_start = begin_at + len(BEGIN)
    assert after[region_start:end_at].strip(), "the region must not be left empty"


def test_a_fresh_install_writes_the_projection_whole(config_root, canonical_root, ds_home):
    """With no file there is nothing to lose, and the generated content carries the
    markers -- so the file is self-maintaining from then on."""
    target = config_root / "CLAUDE.md"
    assert not target.exists()

    _install(config_root, canonical_root, ds_home)

    after = target.read_text(encoding="utf-8")
    assert BEGIN in after and END in after, "a fresh file must land WITH markers"


# -- Task 2: back up before writing, and name the backup ----------------------


def test_a_backup_exists_after_a_write(config_root, canonical_root, ds_home):
    """The old safety_notes claimed "Existing file is backed up before write". A claim in
    a string is not a backup: this asserts the file is on disk AND that its path is
    reported, because a backup nobody can find is not a recovery path.
    """
    target = config_root / "CLAUDE.md"
    original = _marked(body="content that the backup must contain")
    target.write_text(original, encoding="utf-8")

    result = _install(config_root, canonical_root, ds_home)

    entries = [f for f in result["files_written"] if f["path"] == str(target)]
    assert entries, "the CLAUDE.md write must be reported"
    backup_path = entries[0].get("backup_path")
    assert backup_path, "no backup path was reported for a file that already existed"

    backup = Path(backup_path)
    assert backup.is_file(), f"reported backup does not exist on disk: {backup}"
    assert (
        backup.read_text(encoding="utf-8") == original
    ), "the backup must hold the PRE-write content, byte for byte"


def test_the_backup_is_recorded_in_the_manifest(config_root, canonical_root, ds_home):
    """files_written is a return value; the manifest is what SURVIVES the process, and it
    is what an uninstall or a later recovery reads.

    This test first asserted ``result["manifest"]["files"]`` -- a shape I invented rather
    than read. install() returns no manifest key at all; write_manifest() puts it on disk
    at get_manifest_path(). The intent was right and the instrument was guessed, which is
    the same mistake as inventing a fixture value instead of deriving it from the real
    artifact. Reading the file is also the stronger assertion, and the one this
    docstring actually claims: it tests what survives the process.
    """
    target = config_root / "CLAUDE.md"
    target.write_text(_marked(), encoding="utf-8")

    _install(config_root, canonical_root, ds_home)

    manifest_path = get_manifest_path("claude_code", ds_home)
    assert manifest_path.is_file(), f"no manifest was written to {manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    rows = [f for f in manifest["files"] if f.get("path") == str(target)]
    assert rows, f"CLAUDE.md must appear in the on-disk manifest; got {manifest['files']}"
    assert rows[0].get("backup_path"), "the manifest row must carry the backup path"
    assert Path(rows[0]["backup_path"]).is_file(), "the manifest names a backup that is not there"


# -- The contract itself ------------------------------------------------------


def test_merge_refuses_a_half_marked_file():
    """One marker is not a region. Splicing on a lone BEGIN would run to end-of-file and
    swallow everything after it -- the clobber again, wearing the fix's clothes."""
    for existing in (
        f"notes\n{BEGIN}\nbody without an end\n",
        f"notes\nbody without a begin\n{END}\n",
    ):
        text, disposition, detail = merge_claude_md(existing, f"{BEGIN}\nnew\n{END}\n")
        assert text is None, f"a half-marked file must not be written: {existing!r}"
        assert disposition == CLAUDE_MD_REFUSED
        assert detail


def test_merge_refuses_markers_in_the_wrong_order():
    """END before BEGIN yields a negative span. Slicing it would silently produce
    nonsense rather than an error."""
    existing = f"notes\n{END}\nbody\n{BEGIN}\n"
    text, disposition, _ = merge_claude_md(existing, f"{BEGIN}\nnew\n{END}\n")
    assert text is None
    assert disposition == CLAUDE_MD_REFUSED


def test_merge_reports_unchanged_when_the_region_already_matches():
    """An install that rewrites an identical file still churns mtime and burns a backup
    slot. Reporting unchanged lets the caller skip it."""
    generated = f"{BEGIN}\nsame body\n{END}\n"
    existing = _marked(body="same body")
    text, disposition, _ = merge_claude_md(existing, generated)
    assert disposition == CLAUDE_MD_UNCHANGED
    assert text == existing


def test_merge_dispositions_are_distinct_values():
    """Four outcomes the caller branches on; two sharing a value would collapse a
    refusal into a write."""
    assert len({CLAUDE_MD_CREATED, CLAUDE_MD_REFUSED, CLAUDE_MD_SPLICED, CLAUDE_MD_UNCHANGED}) == 4
