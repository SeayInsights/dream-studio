"""The lane container: a reproduction is re-run, and a lie about its exit code is caught.

Lanes replaced hardcoded seats because a seat could claim something was wrong without
testing it (operator, 2026-09-23). The recording door's re-run is what makes that
enforceable rather than hoped for, so its rule is tested here without an engine, and the
container's own properties -- exit codes propagate, no network, nothing persists -- are
tested against a real engine wherever one is running.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from core.gates import lane_sandbox
from core.gates.lane_sandbox import verify_reproduction


def _runner(exit_code, *, timed_out=False):
    def run(image, command):
        return {
            "command": command,
            "exit_code": None if timed_out else exit_code,
            "timed_out": timed_out,
            "output_sha256": "x",
            "output_tail": "",
        }

    return run


def test_a_reproduction_that_reruns_to_the_reported_code_holds():
    holds, run, reason = verify_reproduction(
        "img", {"command": "pytest t.py", "exit_code": 1}, runner=_runner(1)
    )
    assert holds and reason == "reproduced" and run["exit_code"] == 1


def test_a_reported_exit_code_the_rerun_does_not_match_is_refused():
    """The whole point: a reviewer claiming a failure the re-run does not see, or a pass
    the re-run does not see, is refused rather than recorded."""
    holds, _run, reason = verify_reproduction(
        "img", {"command": "pytest t.py", "exit_code": 0}, runner=_runner(1)
    )
    assert not holds
    assert "does not reproduce" in reason


def test_a_timeout_is_neither_a_pass_nor_a_fail():
    holds, _run, reason = verify_reproduction(
        "img", {"command": "sleep 9999", "exit_code": 0}, runner=_runner(0, timed_out=True)
    )
    assert not holds and "timed out" in reason


@pytest.mark.parametrize(
    "repro",
    [{"exit_code": 0}, {"command": "  ", "exit_code": 0}, {"command": "true", "exit_code": "0"}],
)
def test_a_malformed_reproduction_is_refused_without_running(repro):
    def never(image, command):  # pragma: no cover - reaching it is the failure
        raise AssertionError("a malformed reproduction must not be run")

    holds, run, _reason = verify_reproduction("img", repro, runner=never)
    assert not holds and run is None


def test_the_image_is_named_by_the_commit():
    assert lane_sandbox.image_tag("0123456789abcdef" * 2) == "ds-review:0123456789ab"


def test_docker_unavailable_says_so_rather_than_raising(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(lane_sandbox.subprocess, "run", missing)
    ok, why = lane_sandbox.docker_available()
    assert not ok and "not on PATH" in why


# ── against a real engine ───────────────────────────────────────────────────

_ENGINE, _WHY = lane_sandbox.docker_available() if shutil.which("docker") else (False, "no docker")
_IMAGE = "python:3.12-slim"


def _have_image() -> bool:
    if not _ENGINE:
        return False
    if subprocess.run(["docker", "image", "inspect", _IMAGE], capture_output=True).returncode == 0:
        return True
    return subprocess.run(["docker", "pull", "-q", _IMAGE], capture_output=True).returncode == 0


real_engine = pytest.mark.skipif(
    not _have_image(), reason=f"needs a running Docker engine and {_IMAGE}: {_WHY}"
)


@real_engine
def test_real_container_propagates_the_exit_code():
    assert lane_sandbox.run_in_lane(_IMAGE, "exit 3")["exit_code"] == 3
    assert lane_sandbox.run_in_lane(_IMAGE, "true")["exit_code"] == 0


@real_engine
def test_real_container_has_no_network():
    run = lane_sandbox.run_in_lane(
        _IMAGE,
        "python -c \"import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)\"",
    )
    assert run["exit_code"] != 0, "a lane container reached the network"


@real_engine
def test_real_container_keeps_nothing_between_runs():
    """A reviewer may break anything inside; the next run must start clean."""
    lane_sandbox.run_in_lane(_IMAGE, "touch /tmp/left-behind")
    assert lane_sandbox.run_in_lane(_IMAGE, "test -e /tmp/left-behind")["exit_code"] == 1


@real_engine
def test_real_rerun_catches_a_false_claim():
    holds, _run, _reason = verify_reproduction(_IMAGE, {"command": "exit 1", "exit_code": 0})
    assert not holds
