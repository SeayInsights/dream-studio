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
    "quality/architecture",
    "quality/audit",
    "quality/backend-api",
    "quality/database-compliance",
    "quality/frontend-ux",
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


def test_no_mode_claims_a_cli_route_that_no_command_group_backs():
    """The detector must not invent a route any more than it may miss one.

    This asserted `ds-workorder/start` was reachable because `ds work-order start` enters
    it. All three lifecycle packs have since been dissolved -- their operations were always
    commands -- so no mode is CLI-backed any more and the original subject is gone. The
    claim worth keeping is the inverse: PACK_TO_CLI_GROUP must not name a pack that has no
    modes, because a route to nothing is the same defect as a missing route, pointed the
    other way.
    """
    from core.skills.reachability import PACK_TO_CLI_GROUP

    packs_with_modes = {r["pack"] for r in routes()}
    phantom = sorted(set(PACK_TO_CLI_GROUP) - packs_with_modes)
    assert not phantom, f"PACK_TO_CLI_GROUP grants a CLI route to packs with no modes: {phantom}"

    for row in routes():
        assert "cli" not in row["routes"] or row["pack"] in PACK_TO_CLI_GROUP, row


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


def test_a_pack_that_routes_to_its_own_sub_mode_is_a_route_in():
    """THE FOURTH ROUTE, and the detector was wrong without it.

    `ds-website` carries a Mode Routing Table naming all nine sub-modes with their own
    trigger words, so `website/animate` is reachable: the operator says `animate:` and the
    pack dispatches. Counting only triggers, agents and CLI groups reported ten such modes
    as having no way in, which reads as "these are dead" when it is the ordinary way a
    pack with sub-modes works.
    """
    by_mode = {r["mode"]: r for r in routes()}
    for mode in ("website/animate", "website/discover", "fullstack/backend"):
        assert mode in by_mode, f"{mode} was not classified"
        assert (
            "pack" in by_mode[mode]["routes"]
        ), f"{mode} is dispatched by its own pack's routing table and was called unreachable"


def test_un_nesting_made_previously_uncounted_modes_visible():
    """`website` and `fullstack` used to live at `domains/modes/<pack>/`, so their own
    sub-modes sat three levels deep and did not match the `*/modes/*` glob at all. Eleven
    modes were not merely unreachable — they were never counted."""
    modes = {r["mode"] for r in routes()}
    assert "website/animate" in modes and "fullstack/backend" in modes
    assert not any(
        m.startswith("domains/website") or m.startswith("domains/fullstack") for m in modes
    )
