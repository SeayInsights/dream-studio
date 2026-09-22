"""Every agent carries a boundary it can act on.

THE DEFECT. Every compiled agent body ends with the shared contract, which says:

    Stay inside your scope. Work that belongs to another domain is handed back by name.

**No agent was ever shown the names.** A subagent sees its own body and the one skill
inlined into it; it has no way to learn that `quality-database` or `quality-testing`
exist. 23 of 24 agents shipped carrying an instruction whose object they could not
know, which makes it unfollowable — the agent either attempts work outside its domain
or returns a refusal naming nobody, and both are worse than the handoff the contract
asks for.

Subject-matter boundaries are still nobody's to invent. What the registry CAN answer is
which mode dispatches an agent and which siblings exist, and `coverage.yml` records both.
"""

from __future__ import annotations

from unittest import mock

import integrations.compiler.agents as agents_mod
from integrations.compiler.agents import (
    _coverage,
    build_agent,
    derived_scope,
    report_unscoped,
)


def _rows():
    return _coverage()


def test_every_agent_gets_a_scope_section():
    """`scope` used to be rendered only when a `.meta.yml` declared one, and one did."""
    rows = _rows()
    assert len(rows) >= 20, f"only {len(rows)} agents — has coverage.yml been truncated?"
    for row in rows:
        body = build_agent(row)
        assert "## Scope" in body, f"{row['agent']} has no Scope section"


def test_the_scope_names_the_mode_that_dispatches_the_agent():
    for row in _rows():
        assert row["mode"] in derived_scope(row), row["agent"]


def test_the_scope_names_the_siblings_to_hand_work_to():
    """What makes "handed back by name" followable."""
    rows = _rows()
    quality = [r for r in rows if r["mode"].startswith("quality/")]
    assert len(quality) >= 5, "expected several quality specialists"

    row = quality[0]
    scope = derived_scope(row, rows)
    for sibling in quality[1:]:
        assert f"`{sibling['agent']}`" in scope, (
            f"{row['agent']} is not told about {sibling['agent']}, so it cannot hand"
            " work back by name"
        )
    assert (
        f"`{row['agent']}`" not in scope.split("hand work back")[-1]
    ), "an agent is listed as its own neighbour"


def test_a_lone_specialist_is_told_it_is_alone():
    """Naming an empty list of siblings would read as "there is nobody", which is true
    but useless; it needs to know work goes back to the caller."""
    rows = _rows()
    packs = {}
    for r in rows:
        packs.setdefault(r["mode"].split("/")[0], []).append(r)
    lone = [rs[0] for rs in packs.values() if len(rs) == 1]
    if not lone:
        return  # no single-agent pack right now; nothing to assert
    scope = derived_scope(lone[0], rows)
    assert "only" in scope and "caller" in scope


def test_a_hand_written_scope_wins():
    """The derivation is a floor. An author who thought about the boundary knows more
    than the registry does, and must not be overwritten by it."""
    rows = _rows()
    row = dict(rows[0])
    written = "ONLY the thing I was told to do."
    real = agents_mod._load_meta(row)

    def _with_scope(r):
        meta = dict(real)
        meta["scope"] = written
        return meta

    with mock.patch.object(agents_mod, "_load_meta", _with_scope):
        body = build_agent(row)

    section = body.split("## Scope", 1)[1].split("\n## ", 1)[0]
    assert written in section
    assert row["mode"] not in section, "the derivation overwrote a written scope"


def test_the_unscoped_report_still_counts_the_written_ones():
    """The count must keep meaning "nobody wrote a subject-matter boundary", not become
    zero because a floor was added — that would report the gap as closed."""
    unscoped = report_unscoped()
    assert unscoped, "report_unscoped went empty; the derived floor is being miscounted"
