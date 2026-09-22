"""Unit tests for scripts/generate_routing.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from interfaces.cli.generate_routing import (  # noqa: E402
    BEGIN_SENTINEL,
    END_SENTINEL,
    collect_skills,
    generate_routing_block,
    update_claude_md,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    tmp_path: Path, name: str, pack: str, triggers: list[str], description: str = ""
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    desc = description or f"Does {name} things. Trigger on {', '.join(f'`{t}`' for t in triggers)}."
    triggers_yaml = "[" + ", ".join(f'"{t}"' for t in triggers) + "]"
    (skill_dir / "metadata.yml").write_text(
        f'name: {name}\npack: {pack}\ntriggers: {triggers_yaml}\ndescription: "{desc}"\n',
        encoding="utf-8",
    )
    return skill_dir


def _make_claude_md(tmp_path: Path, inner: str = "placeholder content") -> Path:
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        f"# Header\n\n{BEGIN_SENTINEL}\n{inner}\n{END_SENTINEL}\n\n## Footer\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generates_table_from_triggers(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:", "execute plan:"])
    _make_skill(tmp_path, "plan", "core", ["plan:", "/plan"])
    skills = collect_skills(tmp_path / "skills")
    assert len(skills) == 2
    block = generate_routing_block(skills)
    assert "build:" in block
    assert "plan:" in block
    assert "ds-build" in block
    assert "ds-plan" in block


def test_falls_back_to_description_parsing(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "debug"
    skill_dir.mkdir(parents=True)
    (skill_dir / "metadata.yml").write_text(
        "name: debug\npack: quality\ntriggers: []\n"
        'description: "Systematic debugging. Trigger on `debug:`, `diagnose:`."',
        encoding="utf-8",
    )
    skills = collect_skills(tmp_path / "skills")
    assert len(skills) == 1
    assert "debug:" in skills[0]["triggers"]


def test_skips_skill_without_metadata(tmp_path: Path) -> None:
    (tmp_path / "skills" / "orphan").mkdir(parents=True)
    # No metadata.yml — should be silently skipped
    _make_skill(tmp_path, "build", "core", ["build:"])
    skills = collect_skills(tmp_path / "skills")
    names = [s["name"] for s in skills]
    assert "orphan" not in names
    assert "build" in names


def test_idempotent(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:"])
    claude_md = _make_claude_md(tmp_path)

    update_claude_md(claude_md, tmp_path / "skills")
    text_after_first = claude_md.read_text(encoding="utf-8")

    update_claude_md(claude_md, tmp_path / "skills")
    text_after_second = claude_md.read_text(encoding="utf-8")

    assert text_after_first == text_after_second


def test_preserves_content_outside_sentinels(tmp_path: Path) -> None:
    _make_skill(tmp_path, "build", "core", ["build:"])
    header = "# My Header\n\nSome intro prose.\n\n"
    footer = "\n\n## Other Section\nOther content here.\n"
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        f"{header}{BEGIN_SENTINEL}\nold content\n{END_SENTINEL}{footer}",
        encoding="utf-8",
    )

    update_claude_md(path, tmp_path / "skills")
    result = path.read_text(encoding="utf-8")

    assert result.startswith(header)
    assert result.endswith(footer)
    assert "old content" not in result
    assert "ds-build" in result


# ---------------------------------------------------------------------------
# The routing table reaches the skills (F24)
# ---------------------------------------------------------------------------

import pathlib as _pathlib  # noqa: E402

SKILLS_DIR = _pathlib.Path("canonical/skills")


def _collect():
    from interfaces.cli.generate_routing import collect_skills

    return collect_skills(SKILLS_DIR)


def test_both_skill_layouts_are_scanned():
    """The glob read `*/metadata.yml` and matched ONE file. 65 modes live a level deeper
    at `<pack>/modes/<mode>/metadata.yml`; the tree moved to packs-and-modes and the glob
    never followed, so the table that makes a skill discoverable listed 1 of 66."""
    top = list(SKILLS_DIR.glob("*/metadata.yml"))
    modes = list(SKILLS_DIR.glob("*/modes/*/metadata.yml"))
    assert len(modes) > 40, f"only {len(modes)} mode metadata files — has the layout moved?"

    names = {s["name"] for s in _collect()}
    assert (
        len(names) > len(top) + 10
    ), f"only {len(names)} skills collected from {len(top) + len(modes)} metadata files"


def test_block_style_triggers_are_read():
    """YAML has two list spellings and the parser knew one. The block form is what 47 of
    the 65 modes use, and a skill with no triggers is dropped from the table."""
    from interfaces.cli.generate_routing import _parse_triggers

    block = 'name: x\ntriggers:\n  - "intake:"\n  - "sow:"\n'
    inline = "name: x\ntriggers: [intake:, sow:]\n"
    assert _parse_triggers(block) == ["intake:", "sow:"]
    assert _parse_triggers(inline), "the inline form regressed"


def test_an_unquoted_trigger_is_read_rather_than_dropping_the_skill():
    """`- intake:` unquoted parses as {intake: None} — a defect in the metadata, but
    reading it beats unrouting the whole mode over one missing quote."""
    from interfaces.cli.generate_routing import _parse_triggers

    assert _parse_triggers("triggers:\n  - intake:\n  - sow:\n") == ["intake:", "sow:"]


def test_a_pack_nobody_hardcoded_still_routes():
    """PACK_TO_SECTION named four packs, so the whole `domains` pack — eleven modes
    including website, kubernetes, terraform and mobile — fell out unless a mode happened
    to be listed by name in the overrides."""
    collected = _collect()
    names = {s["name"] for s in collected}
    # power-platform, kubernetes, terraform and mobile are all in the `domains` pack,
    # which PACK_TO_SECTION never named.
    domains_modes = {"power-platform", "kubernetes", "terraform", "mobile", "website"}
    assert domains_modes & names, f"no domains mode reaches the table; got {sorted(names)[:8]}"
    assert {s["section"] for s in collected}, "no sections at all"


def test_section_order_is_an_ordering_not_a_filter():
    """The render loop iterated SECTION_ORDER only, so a skill collected under any other
    section was dropped AFTER being counted: the run said 36 registered and wrote 28."""
    from interfaces.cli.generate_routing import SECTION_ORDER, generate_routing_block

    skills = _collect()
    table = generate_routing_block(skills)
    for skill in skills:
        assert skill["name"] in table, (
            f"{skill['name']} was collected under section {skill['section']!r} and did not"
            " render — SECTION_ORDER is filtering again"
        )
    assert any(
        s["section"] not in SECTION_ORDER for s in skills
    ), "no skill sits outside SECTION_ORDER, so this test proves nothing; pick another"


def test_a_skill_that_cannot_route_is_named_not_swallowed():
    """Each of the four ways a skill could leave the table was a bare `continue`, so
    "1 skills registered" read as success while 65 modes were unreachable."""
    from interfaces.cli.generate_routing import collect_skills

    collect_skills(SKILLS_DIR)
    skipped = getattr(collect_skills, "skipped", None)
    assert skipped is not None, "skips are not recorded"
    assert skipped, "nothing skipped — rewrite this test if that became true"
    for name, reason in skipped:
        assert name and reason and len(reason) > 15, (name, reason)


def test_every_metadata_file_is_either_routed_or_named_as_skipped():
    """THE INVARIANT, and what the weaker test missed. Asserting only that *something*
    was skipped passes while one of the two skip paths is deleted, because the other
    still populates the list. Nothing may leave the scan unaccounted for: collected +
    skipped must equal what was read from disk.
    """
    from interfaces.cli.generate_routing import collect_skills

    scanned = {
        *SKILLS_DIR.glob("*/metadata.yml"),
        *SKILLS_DIR.glob("*/modes/*/metadata.yml"),
    }
    collected = collect_skills(SKILLS_DIR)
    skipped = getattr(collect_skills, "skipped", []) or []

    assert len(collected) + len(skipped) == len(scanned), (
        f"{len(scanned)} metadata files scanned, but {len(collected)} routed and"
        f" {len(skipped)} named as skipped — {len(scanned) - len(collected) - len(skipped)}"
        " vanished without explanation"
    )
