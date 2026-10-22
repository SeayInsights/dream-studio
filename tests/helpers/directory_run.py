"""Ask pytest itself what a directory run collects, under a repository's own configuration.

The rule-enforcement gate's resolver (`core/gates/pytest_node_resolver.py`) answers "would a
directory run collect this node" from source. Its tests need an answer that does not come from
the same author's idea of pytest, so they run `pytest --collect-only` and compare. The run is
done with the repository's own addopts, testpaths, norecursedirs and conftest files, none of
them overridden: overriding `addopts` (as an earlier check did with `-o addopts=`) throws away
`--ignore` and `--deselect`, which are the exclusions being checked.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def _node_ids(stdout: str) -> set[str]:
    return {
        line.split("[", 1)[0].strip()
        for line in stdout.splitlines()
        if "::" in line and not line.startswith((" ", "=", "ERROR", "FAILED", "<"))
    }


def directory_run_nodes(root: Path, targets: Sequence[str] = ()) -> set[str]:
    """Every node id `pytest --collect-only` collects in `root` (parameter ids dropped).

    With no `targets` it is a bare run, which starts from the configured `testpaths`; with
    some it is a run over those directories, as `pytest tests/unit` is.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    result = None
    # `-q` prints node ids unless the repo's own addopts carry a `-v` that cancels it, which
    # switches collect-only to a tree; a second `-q` restores the ids. Try the likelier first.
    for quiet in (["-q", "-q"], ["-q"]):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-p",
                "no:cacheprovider",
                *quiet,
                *targets,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
            env=env,
        )
        nodes = _node_ids(result.stdout)
        if nodes:
            assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
            return nodes
    assert result is not None
    raise AssertionError(
        f"a directory run collected nothing:\n{(result.stdout + result.stderr)[-3000:]}"
    )


def would_collect(collected: set[str], node: str) -> bool:
    """A node is collected when it is, or a collected item sits beneath it (a class)."""
    return node in collected or any(c.startswith(node + "::") for c in collected)


def register_nodes(repo_root: Path) -> list[str]:
    """Every pytest node `canonical/rules.yml` names as an enforcer, parameter ids dropped."""
    import yaml

    rules = yaml.safe_load((repo_root / "canonical" / "rules.yml").read_text(encoding="utf-8"))
    return sorted(
        {
            ref.strip().split("[", 1)[0]
            for rule in rules["rules"]
            for ref in rule.get("enforced_by") or []
            if "::" in ref
        }
    )


def disagreements(resolver, nodes: Sequence[str], collected: set[str]):
    """Where the resolver and a directory run give different answers, in both directions.

    Returns (false_alarms, missed, unrun): nodes the resolver refuses that the run collects
    (with the resolver's reason), nodes the resolver accepts that the run does not collect, and
    every node the run does not collect at all.
    """
    verdicts = {n: resolver.resolve(n) for n in nodes}
    false_alarms = {n: why for n, why in verdicts.items() if why and would_collect(collected, n)}
    missed = [n for n, why in verdicts.items() if why is None and not would_collect(collected, n)]
    unrun = [n for n in nodes if not would_collect(collected, n)]
    return false_alarms, missed, unrun
