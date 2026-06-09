"""B.2 — Pre-push gate runner tests.

Exercises core/gates/pre_push.py against synthetic manifests so the runner is
covered without depending on the heavy real gates (black/pytest/etc.).

  * load_manifest                     — reads YAML and surfaces missing files
  * run_gate                          — subprocess success / failure / missing cmd
  * run_pre_push_gates                — stop-on-first-failure and continue modes
  * format_report                     — human-readable rendering
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.gates.pre_push import (
    PrePushReport,
    format_report,
    load_manifest,
    run_gate,
    run_pre_push_gates,
)


def _write_manifest(path: Path, gates: list[dict]) -> None:
    """Write a minimal manifest YAML to ``path``."""
    import yaml as _yaml

    payload = {
        "name": "test-manifest",
        "description": "synthetic",
        "version": 1,
        "gates": gates,
    }
    path.write_text(_yaml.safe_dump(payload), encoding="utf-8")


# ── load_manifest ─────────────────────────────────────────────────────────────


def test_load_manifest_returns_dict(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    _write_manifest(manifest, [{"id": "x", "command": [sys.executable, "-c", "pass"]}])
    data = load_manifest(manifest)
    assert data["name"] == "test-manifest"
    assert data["gates"][0]["id"] == "x"


def test_load_manifest_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "does-not-exist.yaml")


# ── run_gate ──────────────────────────────────────────────────────────────────


def test_run_gate_passes_on_zero_exit(tmp_path: Path) -> None:
    result = run_gate(
        {"id": "ok", "command": [sys.executable, "-c", "print('hello')"]},
        repo_root=tmp_path,
    )
    assert result.passed is True
    assert result.exit_code == 0
    assert "hello" in result.stdout_tail


def test_run_gate_fails_on_nonzero_exit(tmp_path: Path) -> None:
    result = run_gate(
        {
            "id": "bad",
            "command": [sys.executable, "-c", "import sys; sys.exit(2)"],
            "fail_hint": "fix it",
        },
        repo_root=tmp_path,
    )
    assert result.passed is False
    assert result.exit_code == 2
    assert result.fail_hint == "fix it"


def test_run_gate_handles_missing_command(tmp_path: Path) -> None:
    result = run_gate(
        {"id": "nope", "command": ["this-binary-does-not-exist-xyz"]},
        repo_root=tmp_path,
    )
    assert result.passed is False
    assert "not found" in result.fail_hint


def test_run_gate_handles_empty_command(tmp_path: Path) -> None:
    result = run_gate({"id": "empty"}, repo_root=tmp_path)
    assert result.passed is False
    assert "no `command:`" in result.fail_hint


# ── run_pre_push_gates ────────────────────────────────────────────────────────


def test_run_pre_push_gates_all_pass(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "g1", "command": [sys.executable, "-c", "pass"]},
            {"id": "g2", "command": [sys.executable, "-c", "pass"]},
        ],
    )
    report = run_pre_push_gates(manifest_path=manifest, repo_root=tmp_path, emit_events=False)
    assert report.overall_passed is True
    assert len(report.gates) == 2
    assert all(g.passed for g in report.gates)


def test_run_pre_push_gates_stops_on_first_failure(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "g1-fail", "command": [sys.executable, "-c", "import sys; sys.exit(1)"]},
            {"id": "g2-never-runs", "command": [sys.executable, "-c", "pass"]},
        ],
    )
    report = run_pre_push_gates(manifest_path=manifest, repo_root=tmp_path, emit_events=False)
    assert report.overall_passed is False
    assert len(report.gates) == 1
    assert report.gates[0].gate_id == "g1-fail"


def test_run_pre_push_gates_continue_collects_all(tmp_path: Path) -> None:
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "g1-fail", "command": [sys.executable, "-c", "import sys; sys.exit(1)"]},
            {"id": "g2-pass", "command": [sys.executable, "-c", "pass"]},
        ],
    )
    report = run_pre_push_gates(
        manifest_path=manifest,
        repo_root=tmp_path,
        stop_on_first_failure=False,
        emit_events=False,
    )
    assert report.overall_passed is False
    assert len(report.gates) == 2
    assert [g.gate_id for g in report.failed_gates] == ["g1-fail"]


# ── format_report ─────────────────────────────────────────────────────────────


def test_format_report_renders_pass_and_fail() -> None:
    from core.gates.pre_push import GateResult

    report = PrePushReport(
        overall_passed=False,
        gates=[
            GateResult(gate_id="g1", passed=True, exit_code=0, duration_seconds=0.5),
            GateResult(
                gate_id="g2",
                passed=False,
                exit_code=1,
                duration_seconds=1.2,
                fail_hint="run black",
                stderr_tail="some error\nmore detail",
            ),
        ],
    )
    out = format_report(report)
    assert "[PASS] g1" in out
    assert "[FAIL] g2" in out
    assert "hint: run black" in out
    assert "some error" in out
    assert "Overall: FAIL" in out


# ── Advisory tier (AD-3) ──────────────────────────────────────────────────────


def test_advisory_gate_does_not_block_overall_pass(tmp_path: Path) -> None:
    """An advisory gate failure must not set overall_passed=False."""
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {"id": "blocking-pass", "command": [sys.executable, "-c", "pass"], "tier": "blocking"},
            {
                "id": "advisory-fail",
                "command": [sys.executable, "-c", "import sys; sys.exit(1)"],
                "tier": "advisory",
                "warn_hint": "hygiene signal only",
            },
        ],
    )
    report = run_pre_push_gates(manifest_path=manifest, repo_root=tmp_path, emit_events=False)
    assert report.overall_passed is True, "Advisory gate failure must not block overall pass"
    assert len(report.gates) == 2
    assert report.advisory_warnings[0].gate_id == "advisory-fail"
    assert report.failed_gates == []


def test_advisory_gate_continues_after_blocking_fail(tmp_path: Path) -> None:
    """Advisory gates continue running even after a blocking gate failure (stop only applies to blocking)."""
    manifest = tmp_path / "m.yaml"
    _write_manifest(
        manifest,
        [
            {
                "id": "blocking-fail",
                "command": [sys.executable, "-c", "import sys; sys.exit(1)"],
                "tier": "blocking",
            },
            {
                "id": "advisory-after",
                "command": [sys.executable, "-c", "pass"],
                "tier": "advisory",
            },
        ],
    )
    # With stop_on_first_failure=True, the blocking fail should stop the run
    report = run_pre_push_gates(manifest_path=manifest, repo_root=tmp_path, emit_events=False)
    assert report.overall_passed is False
    # Only the blocking gate ran — stop_on_first_failure kicked in
    assert len(report.gates) == 1
    assert report.gates[0].gate_id == "blocking-fail"


def test_format_report_renders_warn_for_advisory() -> None:
    from core.gates.pre_push import GateResult

    report = PrePushReport(
        overall_passed=True,
        gates=[
            GateResult(gate_id="g1", passed=True, exit_code=0, duration_seconds=0.5),
            GateResult(
                gate_id="docs-drift",
                passed=False,
                exit_code=1,
                duration_seconds=0.3,
                tier="advisory",
                warn_hint="update docs when convenient",
            ),
        ],
    )
    out = format_report(report)
    assert "[PASS] g1" in out
    assert "[WARN] docs-drift" in out
    assert "advisory: update docs when convenient" in out
    assert "Overall: PASS" in out
    assert "advisory warning" in out
    assert "[FAIL]" not in out


def test_gate_result_is_advisory_property() -> None:
    from core.gates.pre_push import GateResult

    blocking = GateResult(gate_id="x", passed=True, exit_code=0, duration_seconds=0.0)
    advisory = GateResult(
        gate_id="y", passed=False, exit_code=1, duration_seconds=0.0, tier="advisory"
    )
    assert blocking.is_advisory is False
    assert advisory.is_advisory is True


def test_pre_push_report_advisory_warnings_and_failed_gates() -> None:
    from core.gates.pre_push import GateResult

    report = PrePushReport(
        overall_passed=True,
        gates=[
            GateResult(gate_id="b-pass", passed=True, exit_code=0, duration_seconds=0.0),
            GateResult(
                gate_id="b-fail", passed=False, exit_code=1, duration_seconds=0.0, tier="blocking"
            ),
            GateResult(
                gate_id="a-fail", passed=False, exit_code=1, duration_seconds=0.0, tier="advisory"
            ),
        ],
    )
    assert [g.gate_id for g in report.failed_gates] == ["b-fail"]
    assert [g.gate_id for g in report.advisory_warnings] == ["a-fail"]
