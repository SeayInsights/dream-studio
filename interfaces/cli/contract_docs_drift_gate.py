#!/usr/bin/env python3
"""Release gate for Contract Atlas and documentation freshness drift."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.shared_intelligence.contract_registry import (  # noqa: E402
    change_impact_report,
    contract_registry,
    validate_contract_registry,
)
from interfaces.cli._gate_review_context import (  # noqa: E402
    resolve_base_ref,
    reviewed_no_change_domains as _gather_reviewed_no_change,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help=(
            "Changed file path. May be supplied multiple times. Also readable from the "
            "DREAM_STUDIO_CHANGED_FILES env var (newline/semicolon/comma separated), which "
            "takes priority over any git-based diff -- prefer this flag over exporting that "
            "var, since an ambient value left set in a shell silently replaces detection on "
            "every run made from it, pre-push included."
        ),
    )
    parser.add_argument(
        "--changed-files",
        default=None,
        help="Newline, semicolon, or comma separated changed file paths. See --changed-file.",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        help=(
            "Optional base ref for git diff, for example origin/main. Also readable from the "
            "DREAM_STUDIO_BASE_REF env var, or GITHUB_BASE_REF (prefixed with origin/) when "
            "neither is set."
        ),
    )
    parser.add_argument(
        "--docs-reviewed-no-change",
        action="append",
        default=[],
        help=(
            "Domain id whose impacted docs/contracts were reviewed and need no change. "
            "Also readable from the DREAM_STUDIO_DOCS_REVIEWED_NO_CHANGE env var and from "
            "`Docs-Reviewed-No-Change: <domain_id>` commit trailers in the diff range."
        ),
    )
    args = parser.parse_args()

    changed_files = _changed_files(args)
    reviewed_no_change = _gather_reviewed_no_change(
        cli_domains=args.docs_reviewed_no_change,
        repo_root=REPO_ROOT,
        base_ref=args.base_ref,
    )
    registry_errors = validate_contract_registry(contract_registry())
    report = change_impact_report(
        changed_files,
        reviewed_no_change_domains=reviewed_no_change,
    )
    report["registry_validation_errors"] = registry_errors
    if registry_errors:
        report["status"] = "fail"

    # WO-BYPASS-TELEMETRY: a Docs-Reviewed-No-Change trailer that actually
    # cleared an impacted domain's docs requirement is a gate escape hatch —
    # record which domains it cleared. Best-effort; never changes the outcome.
    # change_impact_report puts each domain's state on "freshness_status" —
    # the top-level "status" is the report's OVERALL pass/fail, a different
    # field entirely (core/shared_intelligence/contract_registry_report.py).
    # Reading "status" here always missed, so this never fired despite firing
    # conditions occurring (WO 48bd8ab3) — a produced value with no reader,
    # now consequential in a second call path (pre-push, not only CI).
    consumed = [
        d.get("domain_id")
        for d in report.get("domains", [])
        if d.get("freshness_status") == "docs_reviewed_no_change_needed"
    ]
    if consumed:
        from core.gates.bypass_event import record_gate_bypass

        record_gate_bypass(
            "docs_drift_reviewed_no_change",
            "Docs-Reviewed-No-Change cleared impacted domains without doc changes",
            extra={"domains": consumed},
        )

    print(json.dumps(report, indent=2, sort_keys=True))

    # stdout stays PURE JSON — callers parse it directly (json.loads(result.stdout)
    # in tests, and any other consumer of this CLI). The operator-facing summary
    # goes to stderr instead: core.gates.pre_push._tail keeps only the LAST 20
    # lines of each stream, and sort_keys=True puts "domains" — with the one
    # thing an operator needs, missing_required_doc_refs — near the TOP of a
    # dump that runs past 500 lines across dozens of domains. Without this, the
    # tail an operator actually sees is almost always unrelated metadata.
    if report["status"] != "pass":
        print(_failure_summary(report), file=sys.stderr)

    raise SystemExit(0 if report["status"] == "pass" else 1)


def _failure_summary(report: dict) -> str:
    """Short, operator-facing account of why this run failed: which domain,
    which docs, which private-artifact or publication pattern. Printed last
    (see main()) so it survives core.gates.pre_push._tail's last-20-lines cut
    where the full JSON dump usually does not."""
    lines = ["contract docs drift: FAIL"]
    for domain in report.get("blocking_domains", []):
        missing = ", ".join(domain.get("missing_required_doc_refs") or []) or "(none listed)"
        lines.append(f"  - {domain.get('domain_id')}: missing required docs: {missing}")
    risk = report.get("publication_risk") or {}
    if risk.get("private_artifact_risk_detected"):
        hits = ", ".join(risk.get("private_artifact_hits") or []) or "(unspecified)"
        lines.append(f"  - private artifact risk: {hits}")
    elif risk.get("publication_risk_detected"):
        hits = ", ".join(risk.get("publication_hits") or []) or "(unspecified)"
        lines.append(f"  - publication risk: {hits}")
    if report.get("registry_validation_errors"):
        lines.append(f"  - registry validation errors: {report['registry_validation_errors']}")
    lines.append(
        "  Refresh the docs named above in this change set, or add an accurate "
        "`Docs-Reviewed-No-Change: <domain_id>` commit trailer if none are needed."
    )
    return "\n".join(lines)


def _changed_files(args: argparse.Namespace) -> list[str]:
    explicit = list(args.changed_file or [])
    if args.changed_files:
        explicit.extend(_split_changed_files(args.changed_files))
    env_value = os.environ.get("DREAM_STUDIO_CHANGED_FILES")
    if env_value:
        explicit.extend(_split_changed_files(env_value))
    if explicit:
        return sorted({item for item in explicit if item})

    base_ref = resolve_base_ref(args.base_ref)
    if base_ref:
        diff = _git_diff_names([base_ref + "...HEAD"])
        if diff is not None:
            # base_ref RESOLVED. Whatever it reports — including a genuinely
            # empty list — IS the answer for what this push changes; falling
            # through to the staged/HEAD/untracked fallback below would
            # instead report unrelated in-progress edits as if they were part
            # of this diff.
            return diff
        # base_ref was NAMED but could not be resolved: no `origin` remote, an
        # unfetched clone, a base branch absent locally. That is not "zero
        # changes" — treating it as such made a file already committed to
        # HEAD invisible whenever the working tree was clean: the
        # staged/HEAD/untracked fallback below only sees UNCOMMITTED state,
        # never what a `git push` would actually publish. A private artifact
        # committed on a first push with no origin remote configured passed
        # this gate silently reporting changed_file_count: 0
        # (WO-DOCS-DRIFT-BLIND-FALLBACK). Enumerate every tracked file
        # instead — conservative (likely over-reports "changed" in this
        # already-degraded mode) but never blind to what is on HEAD.
        tracked = _git_ls_files()
        if tracked is not None:
            return tracked

    pending = _git_changed(["--cached"]) + _git_changed(["HEAD"]) + _git_untracked()
    return sorted(set(pending))


def _split_changed_files(raw: str) -> list[str]:
    normalized = raw.replace(";", "\n").replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def _run_git_names(args: list[str]) -> list[str] | None:
    """Run a read-only `git <args>` and return its output as line-per-name,
    or None if the git binary could not be invoked or it returned non-zero.
    Every git query below is this same shape (invoke, decode leniently,
    split lines); this is the one place that shape is written."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_diff_names(args: list[str]) -> list[str] | None:
    """Like _git_changed, but returns None — never [] — when the git command
    itself failed or the ref could not be resolved, instead of conflating
    that with "the diff genuinely contains zero files". The two cases need
    different fallbacks; see _changed_files."""
    return _run_git_names(["diff", "--name-only", *args])


def _git_ls_files() -> list[str] | None:
    """Every file git tracks at HEAD (plus the index). Used only when
    base_ref names a ref that cannot be resolved: with no comparison point,
    computing what CHANGED is impossible, but listing what EXISTS at HEAD is
    not, and doing so is what stops a file already committed to this branch
    from going unnoticed just because there is no origin/main to diff it
    against."""
    return _run_git_names(["ls-files"])


def _git_changed(args: list[str]) -> list[str]:
    return _git_diff_names(args) or []


def _git_untracked() -> list[str]:
    return _run_git_names(["ls-files", "--others", "--exclude-standard"]) or []


if __name__ == "__main__":
    main()
