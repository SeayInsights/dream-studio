"""
scan_coverage.py -- how much of a scan a parser's result actually covers.

A scanner mode runs several steps and some of them are optional: a header parse that
needs pefile or pyelftools, a second scanner that is skipped when it is not installed,
a platform tool that differs by OS. Before this module a missing tool skipped its step
with no record, and the findings that came out of the remaining steps read as the
result of the whole scan. A clean-looking result from a partial scan is the dangerous
case, so the parsers now say how much of the scan the result covers, using the
vocabulary of docs/contracts/pack-capability-contract.md:

  coverage     complete | partial | unknown
  limitations  strings naming what the result cannot establish

Two facts decide coverage, and both must hold for a step to count:

  1. The run record. The `steps` list in scan-meta.json, written by the mode's own
     "store results" step, says what ran:

         "steps": [
           {"step": "checksec", "status": "ran", "tool": "checksec"},
           {"step": "header_analysis", "status": "skipped", "tool": "pefile",
            "reason": "pefile is not installed"}
         ]

     `status` is `ran`, `skipped` or `failed`; a `ran` step must name its `tool`. The
     existing `scanners` list stays and lists only the scanners that ran.

  2. What the parser read. A step recorded as `ran` is not enough: the parser must also
     have read and parsed a result for it. A result file that is missing, empty, cannot
     be parsed, or is of a kind the parser does not read leaves the step unread, and an
     unread step caps coverage at `partial`.

Rules (see assess()):
  * a planned step skipped, failed, or recorded ran but unread -> partial, each named
  * every planned step recorded as ran and read                -> complete
  * no run record, or a planned step with no usable record     -> unknown, never complete.
    A usable record is exactly one entry for the step with a recognised status, and a
    tool when the status is `ran`. A scan directory written before the run record
    existed lands here, as does a step recorded twice (the record contradicts itself).
    Skipped/unread outranks unknown: it is the more specific known fact.

Everything read out of scan-meta.json is untrusted shape: a malformed entry never raises
and never costs a finding; it reads as an unusable record.

This file is shared by the parse_*.py scripts in this directory; each runs in place and
imports it as a sibling.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path

COMPLETE = "complete"
PARTIAL = "partial"
UNKNOWN = "unknown"

STATUS_RAN = "ran"
STATUS_NOT_RUN = ("skipped", "failed")

META_NAME = "scan-meta.json"

_TEXT_LIMIT = 200


def _text(value: object) -> str:
    """A bounded string for a limitation: scan-meta.json values are arbitrary JSON."""
    s = str(value)
    return s if len(s) <= _TEXT_LIMIT else s[:_TEXT_LIMIT] + "..."


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


def assess(meta: dict | None, planned: tuple[str, ...], read: Iterable[str]) -> dict:
    """Coverage of one scan dir: {"coverage", "skipped_steps", "unread_steps", "limitations"}.

    `planned` is every step the mode would run with all tooling present; `read` is the
    set of planned steps for which the parser actually parsed a result.
    """
    steps = meta.get("steps") if meta is not None else None
    if not isinstance(steps, list):
        why = (
            "scan-meta.json is missing or unreadable"
            if meta is None
            else "scan-meta.json has no run record (`steps`)"
        )
        return {
            "coverage": UNKNOWN,
            "skipped_steps": [],
            "unread_steps": [],
            "limitations": [f"{why}; which steps ran is not known"],
        }

    entries: dict[str, list[dict]] = {}
    for entry in steps:
        if isinstance(entry, dict) and isinstance(entry.get("step"), str):
            entries.setdefault(entry["step"], []).append(entry)

    read = set(read)
    skipped: list[str] = []
    unread: list[str] = []
    limitations: list[str] = []
    unusable: list[tuple[str, str]] = []
    for name in planned:
        records = entries.get(name, [])
        if not records:
            unusable.append((name, "no record of whether it ran"))
            continue
        if len(records) > 1:
            unusable.append((name, f"recorded {len(records)} times, so the record is ambiguous"))
            continue
        entry = records[0]
        status = entry.get("status")
        tool = entry.get("tool")
        if status == STATUS_RAN:
            if not (isinstance(tool, str) and tool.strip()):
                unusable.append((name, "recorded as ran without naming the tool"))
            elif name not in read:
                unread.append(name)
                limitations.append(
                    f"{name} ({_text(tool)}) is recorded as ran but no {name} result was read: "
                    "its output is missing, empty, unparseable, or of a kind the parser "
                    "does not read"
                )
        elif status in STATUS_NOT_RUN:
            skipped.append(name)
            reason = entry.get("reason") or "no reason recorded"
            via = f" ({_text(tool)})" if isinstance(tool, str) and tool.strip() else ""
            limitations.append(f"{name}{via} {status}: {_text(reason)}")
        else:
            unusable.append((name, f"status {_text(status)!r} is not ran, skipped or failed"))

    for name, why in unusable:
        limitations.append(f"{name}: {why}")

    if skipped or unread:
        coverage = PARTIAL
    elif unusable:
        coverage = UNKNOWN
    else:
        coverage = COMPLETE
    return {
        "coverage": coverage,
        "skipped_steps": skipped,
        "unread_steps": unread,
        "limitations": limitations,
    }


def scan_key(result_file: Path, scans_dir: Path) -> tuple[str, Path | None]:
    """The scan directory a result file belongs to, and its scan-meta.json if it has one.

    A scan directory is the directory holding scan-meta.json (the nearest one at or
    below `scans_dir`); a result file with no scan-meta.json above it is its own scan
    directory. Coverage is assessed once per scan directory, never per file.
    """
    meta_path = find_meta(result_file, scans_dir)
    return str(meta_path.parent if meta_path else result_file.parent), meta_path


def scan_dirs(scans_dir: Path, result_files: Iterable[Path]) -> dict[str, Path | None]:
    """Every scan directory under `scans_dir`: key -> its scan-meta.json path (or None).

    Includes directories that hold a scan-meta.json but no result file the parser reads,
    so a scan that skipped everything is still reported. An empty or missing tree yields
    `scans_dir` itself, with no meta, so there is always something to report.
    """
    found: dict[str, Path | None] = {}
    if scans_dir.is_dir():
        for meta_path in sorted(scans_dir.rglob(META_NAME)):
            found[str(meta_path.parent)] = meta_path
    for rf in result_files:
        key, meta_path = scan_key(rf, scans_dir)
        found.setdefault(key, meta_path)
    if not found:
        found[str(scans_dir)] = None
    return found


def assess_all(
    dirs: dict[str, Path | None],
    planned: tuple[str, ...],
    read_by_key: dict[str, set[str]],
) -> dict[str, dict]:
    """Assess every scan directory: key -> {"scan_dir", "coverage", ..., "steps_read"}."""
    out: dict[str, dict] = {}
    for key, meta_path in dirs.items():
        read = read_by_key.get(key, set()) & set(planned)
        report = assess(load_meta(meta_path), planned, read)
        out[key] = {"scan_dir": key, **report, "steps_read": [s for s in planned if s in read]}
    return out


def overall(reports: Iterable[dict]) -> str:
    """One coverage for several scans: partial beats unknown beats complete."""
    values = {r["coverage"] for r in reports}
    if PARTIAL in values:
        return PARTIAL
    if UNKNOWN in values or not values:
        return UNKNOWN
    return COMPLETE


def stamp(findings: list[dict], report: dict) -> None:
    """Carry coverage and limitations on every finding (flat dicts; no schema to migrate)."""
    for f in findings:
        f["coverage"] = report["coverage"]
        f["limitations"] = list(report["limitations"])


def unknown_report(scan_dir: str | None, limitation: str) -> dict:
    """A report for something that was never assessed against a run record."""
    return {
        "scan_dir": scan_dir,
        "coverage": UNKNOWN,
        "skipped_steps": [],
        "unread_steps": [],
        "limitations": [limitation],
        "steps_read": [],
    }


def report(tag: str, reports: list[dict], sidecar: str | Path | None) -> None:
    """Print each scan's coverage to stderr and write the sidecar if one was asked for.

    Call this before every exit, the non-zero ones included: coverage matters most when
    the scan left nothing to parse.
    """
    for r in reports:
        detail = "; ".join(r["limitations"])
        print(
            f"[{tag}] coverage {r['coverage']}: {r['scan_dir']}"
            + (f" -- {detail}" if detail else ""),
            file=sys.stderr,
        )
    if sidecar:
        target = Path(sidecar)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"coverage": overall(reports), "scans": reports}, indent=2),
            encoding="utf-8",
        )
        print(f"[{tag}] Coverage written to {sidecar}", file=sys.stderr)
