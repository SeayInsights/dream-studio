"""The four real-Docker review-lane tests must keep running in CI.

They are ``install_check`` tests, which a default pytest run never collects, and ``ci.yml`` may
not name tests of its own (``test_impact_tests_gate.py``). Their one home is a step in
``full-ci.yml``. Nothing else notices if that step is deleted, pointed at another path, turned
into ``-m "not install_check"``, made non-blocking, or disabled with ``if: false``: the suite
stays green and the operator rule "a review lane executes a reproduction in Docker, and the
recording door re-runs it" quietly stops being tested anywhere.

Both halves are pinned here: the step says exactly what it must, and the tests it runs still
carry the marker that selects them (checked by collection, so it holds on a machine with Docker
as well as on one without, where an unmarked test would just run and pass).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "full-ci.yml"
LANE_TESTS = "tests/unit/test_lane_sandbox.py"

#: The real-engine tests (exit code, no network, nothing persists, a re-run catches a false claim).
ENGINE_TESTS = 4


def _job() -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["full-ci"]


def _lane_steps(job: dict) -> list[dict]:
    return [s for s in job["steps"] if LANE_TESTS in str(s.get("run", ""))]


def test_full_ci_runs_the_lane_engine_tests_in_exactly_one_blocking_step():
    job = _job()
    assert "ubuntu" in str(job["runs-on"]), "Docker is only promised on GitHub's Ubuntu runners"
    assert not job.get("continue-on-error"), "the whole job may not be made non-blocking"

    steps = _lane_steps(job)
    assert len(steps) == 1, (
        f"full-ci.yml must run {LANE_TESTS} in exactly one step, found {len(steps)}: "
        f"{[s.get('name') for s in steps]}"
    )
    step = steps[0]
    assert "if" not in step, f"the step is conditional ({step['if']!r}), so it can silently not run"
    assert not step.get("continue-on-error"), "a failing engine test must fail the job"

    argv = shlex.split(step["run"])
    assert argv[:3] == ["python", "-m", "pytest"], argv
    assert "-m" in argv[3:], "without -m install_check these tests are not collected"
    marker = argv[argv.index("-m", 3) + 1]
    assert marker == "install_check", f"-m {marker!r} does not select the engine tests"
    assert LANE_TESTS in argv, argv
    for forbidden in ("--deselect", "--ignore", "-k", "--co", "--collect-only", "--lf", "-x"):
        assert forbidden not in argv, f"{forbidden} narrows or disables the run: {argv}"
    assert "||" not in step["run"] and "true" not in argv, "the exit code must reach the runner"


def test_the_step_runs_before_the_parity_gate_so_a_red_gate_cannot_hide_it():
    names = [s.get("name") for s in _job()["steps"]]
    assert "Run local parity release gate" in names
    lane = [i for i, s in enumerate(_job()["steps"]) if LANE_TESTS in str(s.get("run", ""))]
    assert lane and lane[0] < names.index("Run local parity release gate")


def _collect(*marker_args: str) -> list[str]:
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *marker_args,
            LANE_TESTS,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")},
        timeout=300,
    )
    # pyproject's addopts carry -v, which turns ``-q --collect-only`` into the tree form.
    return [
        line.strip().removeprefix("<Function ").removesuffix(">")
        for line in done.stdout.splitlines()
        if line.strip().startswith("<Function ")
    ]


def test_the_engine_tests_are_the_ones_the_marker_selects_and_nothing_else_is():
    selected = _collect("-m", "install_check")
    assert len(selected) == ENGINE_TESTS, (
        f"-m install_check must select the {ENGINE_TESTS} real-engine tests of {LANE_TESTS}, "
        f"got {selected}. A test that lost the marker runs by default instead -- and on a "
        "machine with Docker it passes, so nothing else would notice."
    )
    default = _collect()
    assert not set(selected) & set(default), "an engine test is collected by a default run"
    assert len(default) >= 8, "the engine-free tests of the file must still run by default"
