"""Pre-push gate runner — reads canonical/workflows/pre-push.yaml and executes
each gate via subprocess. Used by the git pre-push hook (B.3) and exposed via
``ds workflow run pre-push --non-interactive`` (B.3 wiring).

This is intentionally deterministic and shell-driven, not model-driven — the
model-based workflow engine in control/execution/workflow/ is unsuitable for
a hook that must run in <60s with no LLM round-trip.

B.4: each gate failure emits a ``gate.pre_push.failed`` event using
``CanonicalEventEnvelope`` (per the A0 pattern). The session harvester routes
the event to ``reg_gotchas`` so the failing gate becomes a known pattern.
Emission is best-effort — a write failure logs to stderr but never aborts the
pre-push hook itself (the hook's exit code is governed by gate results alone).
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    exit_code: int
    duration_seconds: float
    fail_hint: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass
class PrePushReport:
    overall_passed: bool
    gates: list[GateResult] = field(default_factory=list)

    @property
    def failed_gates(self) -> list[GateResult]:
        return [g for g in self.gates if not g.passed]


def load_manifest(manifest_path: Path | None = None) -> dict[str, Any]:
    """Load and return the pre-push manifest dict."""
    path = manifest_path or DEFAULT_MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"Pre-push manifest not found: {path}")
    try:
        import yaml as _yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load the pre-push manifest.") from exc
    return _yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _tail(text: str, max_lines: int = 20) -> str:
    """Return the last ``max_lines`` of ``text`` as a single string."""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.rstrip()
    return "\n".join(lines[-max_lines:]).rstrip()


def run_gate(
    gate: dict[str, Any],
    *,
    repo_root: Path,
    timeout_seconds: int = 600,
) -> GateResult:
    """Run a single gate as a subprocess and return its result."""
    gate_id = str(gate.get("id") or "<unnamed>")
    command = gate.get("command") or []
    if not command:
        return GateResult(
            gate_id=gate_id,
            passed=False,
            exit_code=-1,
            duration_seconds=0.0,
            fail_hint="Gate has no `command:` defined in manifest.",
        )

    start = time.monotonic()
    try:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.monotonic() - start
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        return GateResult(
            gate_id=gate_id,
            passed=False,
            exit_code=-1,
            duration_seconds=duration,
            fail_hint=f"Gate timed out after {timeout_seconds}s.",
            stdout_tail=_tail(
                (
                    exc.stdout.decode("utf-8", errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else exc.stdout
                )
                if exc.stdout
                else ""
            ),
            stderr_tail=_tail(
                (
                    exc.stderr.decode("utf-8", errors="replace")
                    if isinstance(exc.stderr, bytes)
                    else exc.stderr
                )
                if exc.stderr
                else ""
            ),
        )
    except FileNotFoundError as exc:
        duration = time.monotonic() - start
        return GateResult(
            gate_id=gate_id,
            passed=False,
            exit_code=-1,
            duration_seconds=duration,
            fail_hint=f"Gate command not found: {exc}",
        )

    return GateResult(
        gate_id=gate_id,
        passed=exit_code == 0,
        exit_code=exit_code,
        duration_seconds=duration,
        fail_hint=str(gate.get("fail_hint") or ""),
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
    )


def emit_gate_failure_event(result: GateResult) -> None:
    """Emit a ``gate.pre_push.failed`` event for a failed gate.

    Constructed via ``CanonicalEventEnvelope`` (NOT a hand-built dict) so
    ``schema_version`` is guaranteed — this is the A0 invariant; hand-built
    dicts caused the original spool ingest failure that A0 fixed.

    Best-effort: a spool-write failure is logged to stderr but never raised.
    The pre-push hook's exit code is governed by gate results alone.
    """
    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        from canonical.events.types import EventType
        from emitters.shared.spool_writer import write_envelopes
    except Exception as exc:  # pragma: no cover — defensive import-time guard
        print(f"[pre-push] event emission unavailable: {exc}", file=sys.stderr)
        return

    envelope = CanonicalEventEnvelope(
        event_type=EventType.GATE_PRE_PUSH_FAILED.value,
        session_id=None,
        payload={
            "gate_id": result.gate_id,
            "exit_code": result.exit_code,
            "duration_seconds": round(result.duration_seconds, 2),
            "fail_hint": result.fail_hint,
            "stderr_tail": result.stderr_tail,
            "stdout_tail": result.stdout_tail,
        },
        severity="warning",
        trace={"gate_id": result.gate_id},
    )
    try:
        write_envelopes([envelope])
    except Exception as exc:
        print(
            f"[pre-push] spool write failed for gate.pre_push.failed "
            f"(gate={result.gate_id}): {exc}",
            file=sys.stderr,
        )


def run_pre_push_gates(
    *,
    manifest_path: Path | None = None,
    repo_root: Path | None = None,
    stop_on_first_failure: bool = True,
    emit_events: bool = True,
) -> PrePushReport:
    """Execute the pre-push gates declared in the manifest.

    Default behavior matches ``on_failure: stop`` in the YAML — the first failed
    gate halts the run. Pass ``stop_on_first_failure=False`` to collect every
    gate's status (useful for diagnostic reports).

    Each failed gate emits a ``gate.pre_push.failed`` event via
    ``CanonicalEventEnvelope`` (B.4). Pass ``emit_events=False`` to suppress
    emission in unit tests that should not write to the spool.
    """
    manifest = load_manifest(manifest_path)
    gates: list[dict[str, Any]] = list(manifest.get("gates") or [])
    root = repo_root or REPO_ROOT

    report = PrePushReport(overall_passed=True)
    for gate in gates:
        result = run_gate(gate, repo_root=root)
        report.gates.append(result)
        if not result.passed:
            report.overall_passed = False
            if emit_events:
                emit_gate_failure_event(result)
            if stop_on_first_failure:
                break
    return report


def format_report(report: PrePushReport) -> str:
    """Render the report as a human-readable string for the pre-push hook."""
    lines: list[str] = []
    for gate in report.gates:
        status = "PASS" if gate.passed else "FAIL"
        lines.append(f"[{status}] {gate.gate_id} ({gate.duration_seconds:.1f}s)")
        if not gate.passed:
            if gate.fail_hint:
                lines.append(f"   hint: {gate.fail_hint}")
            if gate.stderr_tail:
                lines.append("   stderr tail:")
                lines.extend(f"     {line}" for line in gate.stderr_tail.splitlines())
            elif gate.stdout_tail:
                lines.append("   stdout tail:")
                lines.extend(f"     {line}" for line in gate.stdout_tail.splitlines())
    lines.append("")
    lines.append("Overall: " + ("PASS" if report.overall_passed else "FAIL"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    report = run_pre_push_gates()
    print(format_report(report))
    return 0 if report.overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
