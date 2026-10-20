"""
scan_coverage.py -- what a scan actually ran, read back from its scan-meta.json.

A scanner mode runs several steps and some of them are optional: a header parse that
needs pefile or pyelftools, a second scanner that is skipped when it is not installed,
a platform tool that differs by OS. Before this module a missing tool skipped its step
with no record, and the findings that came out of the remaining steps read as the
result of the whole scan. A clean-looking result from a partial scan is the dangerous
case, so the parsers now say how much of the scan the result covers, using the
vocabulary of docs/contracts/pack-capability-contract.md:

  coverage     complete | partial | unknown
  limitations  strings naming what the result cannot establish

The run record is the `steps` list in scan-meta.json, written by the mode's own
"store results" step:

    "steps": [
      {"step": "checksec", "status": "ran", "tool": "checksec"},
      {"step": "header_analysis", "status": "skipped", "tool": "pefile",
       "reason": "pefile is not installed"}
    ]

`status` is `ran`, `skipped` or `failed`. The existing `scanners` list stays and now
lists only the scanners that ran.

Rules (see assess()):
  * any planned step skipped or failed            -> partial, each one named with its reason
  * every planned step recorded as ran            -> complete
  * no run record, or a planned step unrecorded   -> unknown, never complete. An old
    scan directory written before the run record existed lands here.

This file is shared by the parse_*.py scripts in this directory; each runs in place and
imports it as a sibling.
"""

from __future__ import annotations

import json
from pathlib import Path

COMPLETE = "complete"
PARTIAL = "partial"
UNKNOWN = "unknown"

STATUS_RAN = "ran"
STATUS_NOT_RUN = ("skipped", "failed")

META_NAME = "scan-meta.json"


def find_meta(start: Path, stop: Path) -> Path | None:
    """The nearest scan-meta.json at or above `start`, never above `stop`."""
    stop = stop.resolve()
    here = start.resolve()
    if here.is_file():
        here = here.parent
    while True:
        candidate = here / META_NAME
        if candidate.is_file():
            return candidate
        if here == stop or here.parent == here:
            return None
        here = here.parent


def load_meta(path: Path | None) -> dict | None:
    """Parse scan-meta.json; None when absent, unreadable or not a JSON object."""
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def assess(meta: dict | None, planned: tuple[str, ...]) -> dict:
    """Coverage of one scan: {"coverage", "skipped_steps", "limitations"}.

    `planned` is every step the mode would run with all tooling present.
    """
    steps = meta.get("steps") if meta else None
    if not isinstance(steps, list):
        why = (
            "scan-meta.json is missing or unreadable"
            if meta is None
            else "scan-meta.json has no run record (`steps`)"
        )
        return {
            "coverage": UNKNOWN,
            "skipped_steps": [],
            "limitations": [f"{why}; which steps ran is not known"],
        }

    recorded: dict[str, dict] = {}
    for entry in steps:
        if isinstance(entry, dict) and isinstance(entry.get("step"), str):
            recorded[entry["step"]] = entry

    skipped: list[str] = []
    limitations: list[str] = []
    unrecorded: list[str] = []
    for name in planned:
        entry = recorded.get(name)
        if entry is None:
            unrecorded.append(name)
            continue
        status = entry.get("status")
        if status == STATUS_RAN:
            continue
        if status in STATUS_NOT_RUN:
            skipped.append(name)
            tool = entry.get("tool")
            reason = entry.get("reason") or "no reason recorded"
            via = f" ({tool})" if tool else ""
            limitations.append(f"{name}{via} {status}: {reason}")
        else:
            unrecorded.append(name)

    for name in unrecorded:
        limitations.append(f"{name}: no usable record of whether it ran")

    if skipped:
        coverage = PARTIAL
    elif unrecorded:
        coverage = UNKNOWN
    else:
        coverage = COMPLETE
    return {"coverage": coverage, "skipped_steps": skipped, "limitations": limitations}


def overall(assessments: list[dict]) -> str:
    """One coverage for several scans: partial beats unknown beats complete."""
    values = {a["coverage"] for a in assessments}
    if PARTIAL in values:
        return PARTIAL
    if UNKNOWN in values or not values:
        return UNKNOWN
    return COMPLETE


def stamp(
    findings: list[dict], assessment: dict, extra_limitations: list[str] | None = None
) -> None:
    """Carry coverage and limitations on every finding (flat dicts; no schema to migrate)."""
    limitations = list(assessment["limitations"]) + list(extra_limitations or [])
    for f in findings:
        f["coverage"] = assessment["coverage"]
        f["limitations"] = list(limitations)
