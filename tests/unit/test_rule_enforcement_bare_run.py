"""The rule-enforcement gate's resolver against a bare `pytest` run of the whole repository.

`test_the_resolver_agrees_with_a_directory_run_over_the_referenced_directories` in
`test_rule_enforcement_gate.py` runs on every push and covers `tests/unit`. This is the same
comparison made from the configured `testpaths` as a whole, so it sees every file the register
names (one lives in `tests/integration`) and also what `testpaths`, a top-level `--ignore` or a
root `collect_ignore` leave out of a plain `pytest`. It collects about ten thousand items
(roughly forty-five seconds on the reference machine), which is too slow to ask of every push,
so the pre-push pin list does not carry it. GitHub CI never runs the pre-push gates, so where it
runs matters: `interfaces/cli/impact_tests_gate.py` selects it into the pr-smoke job whenever a
change touches `canonical/rules.yml`, a pytest config file, a `conftest.py`, a test file the
register names, or the resolver and its helpers (`rule_enforcement_tests`), and Full CI runs it
after every merge to main.
"""

from __future__ import annotations

from pathlib import Path

from core.gates.pytest_node_resolver import NodeResolver
from tests.helpers.directory_run import directory_run_nodes, disagreements, register_nodes

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_resolver_agrees_with_a_bare_run_from_testpaths_on_the_real_register():
    nodes = register_nodes(REPO_ROOT)
    assert len(nodes) >= 100

    collected = directory_run_nodes(REPO_ROOT)  # `pytest`, no arguments: from testpaths
    assert len(collected) > 5000, f"a bare run collected only {len(collected)} items"

    false_alarms, missed, unrun = disagreements(NodeResolver(REPO_ROOT), nodes, collected)
    assert false_alarms == {}, f"the resolver refuses nodes a bare run collects: {false_alarms}"
    assert missed == [], f"the resolver accepts nodes a bare run does not collect: {missed}"
    assert unrun == []
