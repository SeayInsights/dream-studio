"""Which skill modes can be entered, and which nothing can lead you to.

WHY NOT USAGE. The obvious test for a dead skill is "has anyone run it", and that data
does not exist here: skill-usage telemetry is written by a hook, the hook fires only on
an installed runtime, and a developer machine's spool holds gate events and nothing
else. A detector built on absent telemetry reports every skill dead — the
reported-clean-by-not-looking shape, inverted.

So this asks what the repository can answer about itself: is there a route in?

WHAT IT FOUND. 18 of 72 modes declared no `triggers:` in metadata.yml and documented
them in the SKILL.md `## Trigger` section instead — including `security/scan`, the front
door of the whole security pack, whose section reads ``scan:``, ``scan org:``. The router
read only metadata.yml, so those eighteen were written down and unreachable.
"""

from __future__ import annotations

import pathlib

from core.skills.reachability import SKILLS_DIR, routes, unreachable

#: Pinned by NAME, not count: a count that moved would say only "something changed",
#: while a name says which mode, and fixing one is deleting a line. A new unreachable
#: mode fails this test carrying its own id.
KNOWN_UNREACHABLE = {
    "domains/game-dev",
    "quality/architecture",
    "quality/audit",
    "quality/backend-api",
    "quality/database-compliance",
    "quality/frontend-ux",
    "quality/groom",
    "quality/ops",
    "quality/pre-launch",
    "security/dashboard",
}


def test_the_documented_trigger_section_is_read():
    """`security/scan` is the measured case: the security pack's front door, documented
    and unroutable."""
    from interfaces.cli.generate_routing import _parse_skill_trigger_section

    found = _parse_skill_trigger_section(SKILLS_DIR / "security" / "modes" / "scan" / "SKILL.md")
    assert "scan:" in found, found
    assert "scan org:" in found, found


def test_prose_in_the_trigger_section_is_not_a_trigger(tmp_path):
    """The section is prose. "run security scan" describes a trigger; ``scan:`` is one.
    A parser that took every phrase would fill the routing table with sentences."""
    from interfaces.cli.generate_routing import _parse_skill_trigger_section

    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "# X\n\n## Trigger\n`scan:`, `scan org:`, run security scan, `/scan`\n\n## Purpose\nx\n",
        encoding="utf-8",
    )
    found = _parse_skill_trigger_section(skill)
    assert found == ["scan:", "scan org:"], found
    assert not any("run security" in f for f in found)
    assert not any(f.startswith("/") for f in found), "a slash command is the host's surface"


def test_a_skill_with_no_trigger_section_yields_nothing(tmp_path):
    from interfaces.cli.generate_routing import _parse_skill_trigger_section

    skill = tmp_path / "SKILL.md"
    skill.write_text("# X\n\n## Purpose\nnothing here\n", encoding="utf-8")
    assert _parse_skill_trigger_section(skill) == []


def test_every_mode_is_classified():
    rows = routes()
    on_disk = list(SKILLS_DIR.glob("*/modes/*/SKILL.md"))
    assert len(rows) == len(on_disk), "a mode on disk was not classified"
    assert len(rows) > 50, f"only {len(rows)} modes — has the layout moved?"


def test_a_cli_backed_mode_is_not_called_unreachable():
    """`ds-workorder/start` is reached by `ds work-order start`. Calling it unreachable
    would be the detector not knowing how the product works."""
    by_mode = {r["mode"]: r for r in routes()}
    for mode in ("ds-workorder/start", "ds-project/scope", "ds-milestone/status"):
        assert mode in by_mode, mode
        assert by_mode[mode]["routes"], f"{mode} reported unreachable but the CLI enters it"


def test_the_unreachable_set_is_exactly_what_is_pinned():
    found = set(unreachable())
    new = found - KNOWN_UNREACHABLE
    fixed = KNOWN_UNREACHABLE - found
    assert not new, f"newly unreachable mode(s): {sorted(new)}"
    assert not fixed, f"these gained a route — delete them from KNOWN_UNREACHABLE: {sorted(fixed)}"


def test_the_security_pack_is_reachable():
    """It was not. Eight security modes documented triggers the router never read."""
    dead = set(unreachable())
    for mode in ("security/scan", "security/mitigate", "security/dast", "security/comply"):
        assert mode not in dead, f"{mode} has no route in"


def test_cli_groups_are_read_from_the_cli_not_hardcoded():
    """A group removed from `ds` must stop counting as a route without anyone
    remembering to edit a constant."""
    import inspect

    import core.skills.reachability as mod

    source = inspect.getsource(mod._cli_groups)
    assert "--help" in source and "interfaces.cli.ds" in source
    groups = mod._cli_groups()
    assert {"project", "work-order", "milestone"} <= groups, groups


def test_pinned_modes_still_exist_on_disk():
    """Guard the guard: a pinned mode that was deleted would keep this list passing
    while describing nothing."""
    for mode in KNOWN_UNREACHABLE:
        pack, name = mode.split("/")
        assert (SKILLS_DIR / pack / "modes" / name / "SKILL.md").is_file(), mode
