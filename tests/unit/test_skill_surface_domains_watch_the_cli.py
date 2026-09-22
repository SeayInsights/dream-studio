"""The three skill-surface drift domains must watch the CLI, not only the engine.

Each of these domains couples an engine to the skill that documents it, so that changing
`core/work_orders/**` forces a look at `canonical/skills/ds-workorder/SKILL.md`. That is
the right coupling and it was half-wired: an agent does not call the engine, it calls the
CLI, so a new command could ship with the skill never mentioning it and the docs-drift
gate would say nothing.

FOUND BY HITTING IT. `ds project onboard` was written and would have merged undocumented;
the gate stayed silent because `interfaces/cli/commands/project.py` matched no domain's
`source_patterns` — no domain watched `interfaces/cli/commands/**` at all.

Measured before widening, over 200 commits: those CLI modules changed 23 times and 7 of
those commits did not touch the matching skill. So this fires on roughly 3.5% of commits,
and the `Docs-Reviewed-No-Change: <domain>` trailer covers the genuinely cosmetic ones.

The negative cases are the point as much as the positive ones. A pattern broad enough to
catch every CLI change would make the gate noise, and noise is how a signal gets switched
off — so `integrate.py` and `system.py` must stay unmatched.
"""

from __future__ import annotations

import pytest

from core.shared_intelligence.contract_registry_report import change_impact_report

SKILL_SURFACE_DOMAINS = {
    "projects_engine_skill_surface",
    "milestones_engine_skill_surface",
    "work_orders_engine_skill_surface",
}


def _skill_domains_hit(path: str) -> set[str]:
    report = change_impact_report([path])
    impacted = {d["domain_id"] for d in report["domains"] if d.get("impacted")}
    return impacted & SKILL_SURFACE_DOMAINS


@pytest.mark.parametrize(
    "path,domain",
    [
        ("interfaces/cli/commands/project.py", "projects_engine_skill_surface"),
        ("interfaces/cli/commands/milestone.py", "milestones_engine_skill_surface"),
        # All five work-order CLI modules, because the pattern is a glob and a glob that
        # silently stops matching a sibling is the failure this is guarding against.
        ("interfaces/cli/commands/work_order.py", "work_orders_engine_skill_surface"),
        ("interfaces/cli/commands/work_order_query.py", "work_orders_engine_skill_surface"),
        ("interfaces/cli/commands/work_order_tasks.py", "work_orders_engine_skill_surface"),
        ("interfaces/cli/commands/work_order_lifecycle.py", "work_orders_engine_skill_surface"),
        ("interfaces/cli/commands/work_order_dispatch.py", "work_orders_engine_skill_surface"),
    ],
)
def test_the_cli_surface_impacts_the_skill_that_documents_it(path, domain):
    assert _skill_domains_hit(path) == {domain}


@pytest.mark.parametrize(
    "path,domain",
    [
        ("core/projects/mutations.py", "projects_engine_skill_surface"),
        ("core/milestones/mutations.py", "milestones_engine_skill_surface"),
        ("core/work_orders/mutations.py", "work_orders_engine_skill_surface"),
    ],
)
def test_the_engine_half_still_works(path, domain):
    """Widening must ADD the CLI, never replace the engine coupling that already held."""
    assert _skill_domains_hit(path) == {domain}


@pytest.mark.parametrize(
    "path",
    [
        "interfaces/cli/commands/integrate.py",
        "interfaces/cli/commands/system.py",
        "interfaces/cli/commands/system_health.py",
    ],
)
def test_an_unrelated_cli_module_does_not_demand_a_skill_review(path):
    """The negative half. A blocking gate that fires on every CLI edit teaches people to
    reach for the escape hatch, and an escape hatch that costs nothing becomes the norm."""
    assert _skill_domains_hit(path) == set()


def test_every_cli_module_a_domain_names_actually_exists():
    """A pattern that matches nothing reports clean forever — the shape this whole file
    exists to catch, one level up. Literal paths are checked against the tree; a glob is
    checked by requiring that it matches at least one file."""
    from pathlib import Path

    from core.shared_intelligence.contract_registry import contract_registry

    repo = Path(__file__).resolve().parents[2]
    checked = 0
    for domain in contract_registry()["domains"]:
        if domain["domain_id"] not in SKILL_SURFACE_DOMAINS:
            continue
        for pattern in domain["source_patterns"]:
            if not pattern.startswith("interfaces/"):
                continue
            checked += 1
            if "*" in pattern:
                assert list(repo.glob(pattern)), f"{pattern} matches no file in the tree"
            else:
                assert (repo / pattern).is_file(), f"{pattern} names a file that does not exist"
    assert checked == 3, f"expected one CLI pattern per skill-surface domain, found {checked}"
