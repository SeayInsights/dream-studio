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

from core.gates import registry as _registry

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "canonical" / "workflows" / "pre-push.yaml"


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    exit_code: int
    duration_seconds: float
    tier: str = "blocking"  # "blocking" or "advisory" (AD-3 two-tier model)
    fail_hint: str = ""
    warn_hint: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def is_advisory(self) -> bool:
        return self.tier == "advisory"


@dataclass
class PrePushReport:
    overall_passed: bool
    gates: list[GateResult] = field(default_factory=list)

    @property
    def failed_gates(self) -> list[GateResult]:
        """Gates that failed AND are blocking (advisory failures are warnings, not failures)."""
        return [g for g in self.gates if not g.passed and not g.is_advisory]

    @property
    def advisory_warnings(self) -> list[GateResult]:
        """Advisory gates that failed (surfaced but do not block overall pass)."""
        return [g for g in self.gates if not g.passed and g.is_advisory]


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
    """Run a single gate and return its result.

    C12: a gate this repository owns (not a third-party tool, and only when running
    against this repository's own checkout — see core/gates/registry.py) runs IN-PROCESS
    by importing its module and calling its own main() directly, rather than paying a
    fresh interpreter's startup cost for a check that is itself single-digit
    milliseconds. Gate env overrides are a real behavior difference the in-process path
    cannot honor (they would leak into this process for every gate after), so a gate
    declaring one always runs as a subprocess regardless of registry eligibility.
    """
    gate_id = str(gate.get("id") or "<unnamed>")
    tier = str(gate.get("tier") or "blocking")
    command = gate.get("command") or []
    if not command:
        return GateResult(
            gate_id=gate_id,
            passed=False,
            exit_code=-1,
            duration_seconds=0.0,
            tier=tier,
            fail_hint="Gate has no `command:` defined in manifest.",
        )

    gate_env = gate.get("env") or {}
    if not gate_env:
        start = time.monotonic()
        in_process = _registry.run_in_process(gate_id, command, repo_root=repo_root)
        if in_process is not None:
            exit_code, stdout, stderr = in_process
            duration = time.monotonic() - start
            return GateResult(
                gate_id=gate_id,
                passed=exit_code == 0,
                exit_code=exit_code,
                duration_seconds=duration,
                tier=tier,
                fail_hint=str(gate.get("fail_hint") or ""),
                warn_hint=str(gate.get("warn_hint") or ""),
                stdout_tail=_tail(stdout),
                stderr_tail=_tail(stderr),
            )

    # Merge gate-level env overrides into the current process environment.
    run_env = {**__import__("os").environ, **{str(k): str(v) for k, v in gate_env.items()}}

    start = time.monotonic()
    try:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            # WO-LOCALE-DECODE-SILENT-LOSS: text=True alone decodes with
            # locale.getpreferredencoding(False) — cp1252 on Windows. Gates emit UTF-8,
            # so a byte cp1252 leaves unmapped (a ❌ or ← is enough) raised
            # UnicodeDecodeError in subprocess's reader THREAD; this call then returned
            # returncode=0 with stdout=None, and the tails below silently became empty.
            # Exit codes still decided the verdict, so what was lost was the gate's
            # diagnostic — a failure with no reason attached. errors="replace" because a
            # gate must report on odd bytes, not vanish on them. (The TimeoutExpired
            # handler below already decoded UTF-8 explicitly; this path was missed.)
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=run_env,
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
        tier=tier,
        fail_hint=str(gate.get("fail_hint") or ""),
        warn_hint=str(gate.get("warn_hint") or ""),
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
    )


def emit_gate_failure_event(result: GateResult, repo_root: Path | None = None) -> None:
    """Emit a ``gate.pre_push.failed`` event for a failed gate.

    Constructed via ``CanonicalEventEnvelope`` (NOT a hand-built dict) so
    ``schema_version`` is guaranteed — this is the A0 invariant; hand-built
    dicts caused the original spool ingest failure that A0 fixed.

    Best-effort: a spool-write failure is logged to stderr but never raised.
    The pre-push hook's exit code is governed by gate results alone.
    """
    if not _telemetry_home_exists():
        return

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
            **_judged_repo(repo_root),
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


def _telemetry_home_exists() -> bool:
    """Is there a Dream Studio runtime for this telemetry to land in?

    TELEMETRY MUST NOT CREATE THE RUNTIME IT REPORTS INTO. The spool root defaults
    to `~/.dream-studio/events`, and `write_event` makes its directories, so every
    gate run wrote one event per gate and rebuilt a home the operator had
    deliberately uninstalled -- 20 files per push, from a feature added to record
    gate outcomes. The operator removed the install; the checks kept putting it
    back.

    So emission is conditional on the home already being there. A repository
    checkout is not an install: these gates are ordinary Python and run fine with
    no Dream Studio present, and in that state there is nothing to report to.
    DS_SPOOL_ROOT still wins, which is how CI keeps recording.
    """
    import os

    from core.installed_runtime import CONFIG_RELATIVE_PATH

    if os.environ.get("DS_SPOOL_ROOT"):
        return True
    # AN INSTALL, NOT A DIRECTORY. The first version checked that ~/.dream-studio
    # existed -- and a single stray write creates it: on 2026-09-23 a mutation run with
    # `--home` elsewhere leaked its event into the default spool, the directory appeared,
    # and this guard then let 514 gate events into a home nobody had installed. Only the
    # installer writes config/runtime.json.
    from core.config.paths import home_dir

    home = home_dir()
    return (home / CONFIG_RELATIVE_PATH).is_file()


def _judged_repo(repo_root: Path | None) -> dict[str, object]:
    """Which repository this outcome is about.

    WHY THIS IS NOT OPTIONAL. `--repo <path>` runs another project's own gates, and the
    events landed in Dream Studio's spool carrying `gate_id` and nothing else -- so a
    foreign project's gate outcome was byte-indistinguishable from one of this
    repository's own. Found by reading the live spool after the `--repo` flag shipped:
    a gate named `says-hello`, which exists only in a throwaway test project, sat beside
    23 real ones with no way to tell them apart.

    Any later question of the form "how often does this gate fail" silently mixes two
    populations, and the answer is wrong in a direction nobody would notice.
    """
    root = Path(repo_root).resolve() if repo_root else REPO_ROOT
    return {"repo": str(root), "repo_is_self": root == REPO_ROOT}


def emit_gate_outcome_event(result: GateResult, repo_root: Path | None = None) -> None:
    """Emit ``gate.pre_push.completed`` for a gate that ran, whatever it decided.

    WHY A SECOND EVENT. ``gate.pre_push.failed`` records blocking failures only,
    so the authority held 649 failures, 408 bypasses and zero passes. That is a
    numerator without a denominator: a gate with no recorded failures might be
    perfect prevention or might be dead, and nothing could tell them apart. Nine
    of the seventeen gates wired today have never once appeared in a failure
    record, and no query could say which kind of nine they are.

    ADVISORY FAILURES WERE RECORDED NOWHERE AT ALL. The run loop read
    ``if result.is_advisory: pass``, so an advisory gate that failed produced no
    event of any kind -- the one tier whose whole purpose is to surface a signal
    without blocking was the tier that surfaced nothing.

    Emitted BESIDE the failure event rather than replacing it, because 649 rows
    and whatever reads them keep working unchanged.

    Best-effort, exactly like its sibling: a spool-write failure is printed and
    never raised. The push's exit code is governed by gate results alone.
    """
    if not _telemetry_home_exists():
        return

    try:
        from canonical.events.envelope import CanonicalEventEnvelope
        from canonical.events.types import EventType
        from emitters.shared.spool_writer import write_envelopes
    except Exception as exc:  # pragma: no cover — defensive import-time guard
        print(f"[pre-push] outcome emission unavailable: {exc}", file=sys.stderr)
        return

    if result.passed:
        outcome = "passed"
    elif result.is_advisory:
        outcome = "advisory_failed"
    else:
        outcome = "failed"

    envelope = CanonicalEventEnvelope(
        event_type=EventType.GATE_PRE_PUSH_COMPLETED.value,
        session_id=None,
        payload={
            "gate_id": result.gate_id,
            "outcome": outcome,
            "passed": result.passed,
            "advisory": result.is_advisory,
            "exit_code": result.exit_code,
            "duration_seconds": round(result.duration_seconds, 2),
            **_judged_repo(repo_root),
        },
        severity="info" if result.passed else "warning",
        trace={"gate_id": result.gate_id, "outcome": outcome},
    )
    try:
        write_envelopes([envelope])
    except Exception as exc:
        print(
            f"[pre-push] spool write failed for gate.pre_push.completed "
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
        # EVERY outcome is recorded, including the ones that change nothing.
        # Recording only blocking failures gave the authority 649 failures and
        # zero passes, so "has this gate ever fired" had no answer and a dead
        # gate was indistinguishable from a gate that prevents.
        if emit_events:
            emit_gate_outcome_event(result, repo_root=root)
        if not result.passed:
            if result.is_advisory:
                # Advisory failures surface as warnings but never block push.
                # They used to emit nothing at all -- the one tier meant to
                # surface a signal without blocking surfaced none.
                pass
            else:
                report.overall_passed = False
                if emit_events:
                    emit_gate_failure_event(result, repo_root=root)
                if stop_on_first_failure:
                    break
    return report


def format_report(report: PrePushReport) -> str:
    """Render the report as a human-readable string for the pre-push hook."""
    lines: list[str] = []
    for gate in report.gates:
        if gate.passed:
            status = "PASS"
        elif gate.is_advisory:
            status = "WARN"
        else:
            status = "FAIL"
        lines.append(f"[{status}] {gate.gate_id} ({gate.duration_seconds:.1f}s)")
        if not gate.passed:
            hint = gate.warn_hint if gate.is_advisory else gate.fail_hint
            if hint:
                lines.append(f"   {'advisory' if gate.is_advisory else 'hint'}: {hint}")
            # Both streams, not stderr-or-stdout. The `elif` here dropped stdout
            # whenever stderr held anything at all, and for a pytest gate that is
            # backwards: the failing assertion is on stdout while stderr carries
            # only an unrelated import warning. A pin-tests failure therefore
            # printed its hint and nothing else, and the only way to learn WHICH
            # pin drifted was to re-run the gate by hand — the same
            # failure-with-no-reason-attached shape as the codec defect this WO
            # started from (WO-LOCALE-DECODE-SILENT-LOSS).
            if gate.stdout_tail:
                lines.append("   stdout tail:")
                lines.extend(f"     {line}" for line in gate.stdout_tail.splitlines())
            if gate.stderr_tail:
                lines.append("   stderr tail:")
                lines.extend(f"     {line}" for line in gate.stderr_tail.splitlines())
    lines.append("")
    lines.append("Overall: " + ("PASS" if report.overall_passed else "FAIL"))
    if report.advisory_warnings:
        lines.append(f"  ({len(report.advisory_warnings)} advisory warning(s) — push not blocked)")
    return "\n".join(lines)


def _print_report(text: str) -> None:
    """Print the report without the encoder deciding whether the gates ran.

    A gate's captured output is decoded with errors="replace", so a byte the
    child's encoding could not express arrives here as U+FFFD; the report also
    carries em dashes from the gate descriptions. Printing either to a cp1252
    stdout raises UnicodeEncodeError -- which is what a redirected run on Windows
    gets, and redirecting is exactly what this repo's own instructions tell
    people to do. The whole suite then passed and the process still exited on a
    traceback from its own last line.

    Reconfiguring is tried first so the text survives intact. If that is refused
    the text is coerced through the live encoding, losing characters rather than
    the result: a mangled report still says which gate failed, and a traceback
    says nothing.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def main(argv: list[str] | None = None) -> int:
    """Run this repository's gates, or another project's own.

    ``argv`` was accepted and never read: the body called `run_pre_push_gates()` with
    no arguments, so `manifest_path` and `repo_root` -- both long-standing parameters --
    had no caller that set them. The capability was built and had no door.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the pre-push gates for this repository, or for another project."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=(
            "Run THAT project's own gates, declared in its tree"
            " (.dream-studio/gates.yaml, or canonical/workflows/pre-push.yaml)."
            " A project declaring none is refused rather than gated on Dream Studio's"
            " rules, which would fail for reasons about Dream Studio."
        ),
    )
    args = parser.parse_args(argv)

    manifest_path = None
    repo_root = None
    if args.repo:
        from core.projects.standards import gate_manifest_for

        repo_root = Path(args.repo).resolve()
        manifest_path, refusal = gate_manifest_for(repo_root)
        if refusal:
            print(f"pre-push: {refusal}", file=sys.stderr)
            return 2

    report = run_pre_push_gates(manifest_path=manifest_path, repo_root=repo_root)
    _print_report(format_report(report))
    return 0 if report.overall_passed else 1


if __name__ == "__main__":
    sys.exit(main())
