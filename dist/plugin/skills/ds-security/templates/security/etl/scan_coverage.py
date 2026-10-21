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
     unread step caps coverage at `partial`. Results are read only from the exact
     documented file names directly in the scan directory (split_by_scan_dir); a stale
     subdirectory copy or a wrongly named file is ignored and named. A step read only
     in part (a cap dropped records, values were ignored) is `partial` as well: the
     parser reports that as `degraded`.

Rules (see assess()):
  * a planned step skipped, failed, ran but unread, or read only partly -> partial, each named
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

import codecs
import json
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

COMPLETE = "complete"
PARTIAL = "partial"
UNKNOWN = "unknown"

STATUS_RAN = "ran"
STATUS_NOT_RUN = ("skipped", "failed")

META_NAME = "scan-meta.json"

_TEXT_LIMIT = 200


def short(value: object) -> str:
    """A bounded, single-line, printable string for a limitation or finding field.

    Values come from scan-meta.json and result files, which are arbitrary: they may be
    huge, nested, or carry newlines and terminal escapes. Control characters are dropped.
    """
    s = "".join(ch for ch in str(value) if ch.isprintable())
    return s if len(s) <= _TEXT_LIMIT else s[:_TEXT_LIMIT] + "..."


_text = short


class Read(NamedTuple):
    """What reading one result file produced.

    `step` is the planned step the file is the output of, None when it is not a result
    this parser reads. `degraded` are reasons the step was read only partly (records
    dropped by a cap, values ignored): they make the step, and so the scan, partial.
    `notes` are limitations that hold without lowering coverage (undecodable bytes
    replaced, a check name the doc does not list). `refusals` say why a file was found and
    not accepted as the step's result (it is not that step's output, it has the wrong
    shape): they are never cut by the note cap, because the unread-step limitation points
    at them.
    """

    step: str | None
    findings: list
    degraded: list
    notes: list
    refusals: list | tuple = ()


class ScanRead:
    """Everything the parser learned about one scan directory, for assess_all().

    `refusals` (a file found and not read: it could not be read, is not the step's output,
    could not be placed) are kept in full. `notes` are bounded, and `ignored` (a file not
    named like a result, or left in a subdirectory) is what the bound cuts first.
    """

    def __init__(self) -> None:
        self.steps: set[str] = set()
        self.degraded: dict[str, list[str]] = {}
        self.notes: list[str] = []
        self.refusals: list[str] = []
        self.ignored: list[str] = []

    def add(self, result: Read) -> None:
        if result.step is not None:
            self.steps.add(result.step)
            if result.degraded:
                self.degraded.setdefault(result.step, []).extend(result.degraded)
        self.notes.extend(result.notes)
        self.refusals.extend(result.refusals)


def _real(path: Path) -> Path:
    """Absolute, links followed, `..` collapsed. The one form every comparison uses."""
    return Path(os.path.realpath(path))


def _norm(path: Path | str) -> str:
    """Comparison key for a directory: case-folded on Windows, separators normalised."""
    return os.path.normcase(os.path.normpath(str(path)))


Resolver = Callable[[Path], Path]


def find_meta(start: Path, stop: Path, resolve: Resolver = _real) -> Path | None:
    """The nearest scan-meta.json at or above `start`, never above `stop`.

    Both are resolved with `resolve` first, so a relative path, a path through a link or a
    differently-cased one reaches the same answer as the absolute path.
    """
    stop = resolve(stop)
    here = resolve(start)
    if here.is_file():
        here = here.parent
    while True:
        candidate = here / META_NAME
        if candidate.is_file():
            return candidate
        if _norm(here) == _norm(stop) or here.parent == here:
            return None
        here = here.parent


# -- text encodings -----------------------------------------------------------------------------------
#
# Windows tools do not write UTF-8: PowerShell 5.1's `>` writes UTF-16 LE with a BOM, Notepad
# and `Out-File` may add a UTF-8 BOM. Read as UTF-8 with replacement, a UTF-16 file turns
# into text with a NUL between every character, and a credential scan quietly finds nothing.
# decode_text() recognises what a BOM or an unmistakable NUL pattern says, decodes it, and
# says so; content that is not text in a supported encoding raises instead of being guessed.

#: Bytes the decoder could not decode in the current decode_text() call: a count, not a list.
#: (A list with one entry per decoder error cost 20 million entries for a 20 MB file of
#: nothing but bad bytes.) A one-cell list because the error handler is a plain function.
_BAD_BYTES = [0]


def _count_bad(exc: UnicodeError) -> tuple[str, int]:
    _BAD_BYTES[0] += exc.end - exc.start
    return "�", exc.end


codecs.register_error("scan_coverage_count", _count_bad)

_BOMS = (  # UTF-32 LE starts with the UTF-16 LE BOM, so it is tried first
    (codecs.BOM_UTF32_LE, "utf-32", "UTF-32 LE (BOM)"),
    (codecs.BOM_UTF32_BE, "utf-32", "UTF-32 BE (BOM)"),
    (codecs.BOM_UTF8, "utf-8-sig", "UTF-8 BOM"),
    (codecs.BOM_UTF16_LE, "utf-16", "UTF-16 LE (BOM)"),
    (codecs.BOM_UTF16_BE, "utf-16", "UTF-16 BE (BOM)"),
)


class Decoded(NamedTuple):
    """Text, plus `notes` (the encoding was not plain UTF-8) and `degraded` (bytes were
    replaced, so the text may be misread)."""

    text: str
    notes: list
    degraded: list


def _guess_utf16(data: bytes) -> tuple[str, str] | None:
    """UTF-16 without a BOM: ASCII-range text has a NUL in every other byte."""
    if len(data) < 4:
        return None
    even, odd = data[0::2], data[1::2]
    if odd.count(0) >= 0.8 * len(odd) and even.count(0) <= 0.1 * len(even):
        return "utf-16-le", "UTF-16 LE (no BOM)"
    if even.count(0) >= 0.8 * len(even) and odd.count(0) <= 0.1 * len(odd):
        return "utf-16-be", "UTF-16 BE (no BOM)"
    return None


def decode_text(data: bytes, name: str) -> Decoded:
    """Decode a result file's bytes. Raises ValueError for content that is not text.

    Not text: a NUL after decoding, or more than a tenth of the bytes undecodable. A few
    undecodable bytes are replaced and reported in `degraded` (the step is then partial).
    A U+FFFD that is really in the file is not counted: only the decoder's own errors are.
    """
    encoding, label = "utf-8", None
    for bom, codec, bom_label in _BOMS:
        if data.startswith(bom):
            encoding, label = codec, bom_label
            break
    else:
        guessed = _guess_utf16(data)
        if guessed:
            encoding, label = guessed
    _BAD_BYTES[0] = 0
    text = data.decode(encoding, errors="scan_coverage_count")
    bad = _BAD_BYTES[0]

    if "\x00" in text:
        raise ValueError(
            "it contains NUL characters, so it is not text in UTF-8, UTF-16 or UTF-32; "
            "write result files as UTF-8"
        )
    if bad * 10 > len(data):
        raise ValueError(f"{bad} of its {len(data)} bytes are not valid text in {label or 'UTF-8'}")
    notes: list[str] = []
    degraded: list[str] = []
    if label == "UTF-8 BOM":
        notes.append(f"{name} starts with a UTF-8 BOM, which was ignored")
    elif label:
        notes.append(f"{name} is encoded as {label}; it was decoded, but write results as UTF-8")
    if bad:
        degraded.append(
            f"{bad} undecodable byte(s) in {name} were replaced; the lines holding them "
            "may be misread"
        )
    return Decoded(text, notes, degraded)


def load_meta(path: Path | None) -> dict | None:
    """Parse scan-meta.json; None when absent, unreadable or not a JSON object.

    Read through decode_text, so a BOM or UTF-16 written by a Windows tool still parses.
    """
    if path is None:
        return None
    try:
        data = json.loads(decode_text(path.read_bytes(), path.name).text)
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def assess(
    meta: dict | None,
    planned: tuple[str, ...],
    read: Iterable[str],
    degraded: dict[str, list[str]] | None = None,
) -> dict:
    """Coverage of one scan dir: {"coverage", "skipped_steps", "unread_steps",
    "degraded_steps", "limitations"}.

    `planned` is every step the mode would run with all tooling present; `read` is the
    set of planned steps for which the parser actually parsed a result; `degraded` maps
    a read step to the reasons it was read only partly (a cap dropped records, values
    were ignored). A step recorded ran and read but degraded is partial.
    """
    degraded = degraded or {}
    run_partial, run_unknown, run_limitations = _assess_run(meta)
    steps = meta.get("steps") if meta is not None else None
    if not isinstance(steps, list):
        why = (
            "scan-meta.json is missing or unreadable"
            if meta is None
            else "scan-meta.json has no run record (`steps`)"
        )
        return {
            # A CI run that did not succeed is a known fact, and the more specific one.
            "coverage": PARTIAL if run_partial else UNKNOWN,
            "skipped_steps": [],
            "unread_steps": [],
            "degraded_steps": [],
            "limitations": [f"{why}; which steps ran is not known", *run_limitations],
        }

    entries: dict[str, list[dict]] = {}
    for entry in steps:
        if isinstance(entry, dict) and isinstance(entry.get("step"), str):
            entries.setdefault(entry["step"], []).append(entry)

    read = set(read)
    skipped: list[str] = []
    unread: list[str] = []
    partly: list[str] = []
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
                    "the documented result file is missing, unparseable, or not that step's "
                    "output (a file that was found and refused is named in another limitation)"
                )
            elif degraded.get(name):
                partly.append(name)
                reasons = "; ".join(short(r) for r in degraded[name])
                limitations.append(f"{name} ({_text(tool)}) was read only partly: {reasons}")
        elif status in STATUS_NOT_RUN:
            skipped.append(name)
            reason = entry.get("reason") or "no reason recorded"
            via = f" ({_text(tool)})" if isinstance(tool, str) and tool.strip() else ""
            limitations.append(f"{name}{via} {status}: {_text(reason)}")
        else:
            unusable.append((name, f"status {_text(status)!r} is not ran, skipped or failed"))

    for name, why in unusable:
        limitations.append(f"{name}: {why}")
    limitations.extend(run_limitations)

    if skipped or unread or partly or run_partial:
        coverage = PARTIAL
    elif unusable or run_unknown:
        coverage = UNKNOWN
    else:
        coverage = COMPLETE
    return {
        "coverage": coverage,
        "skipped_steps": skipped,
        "unread_steps": unread,
        "degraded_steps": partly,
        "limitations": limitations,
    }


def _assess_run(meta: dict | None) -> tuple[bool, bool, list[str]]:
    """What scan-meta.json says about the run as a whole: (partial, unknown, limitations).

    Two whole-run facts, beyond the per-step record. `outcome: not_scanned` (a target the
    mode did not scan at all) is partial and names the reason. And modes whose scan is one
    CI workflow run record it (`scan ingest`):

        "run": {"run_id": "123", "status": "completed", "conclusion": "failure"}

    A run that did not conclude `success` (failure, cancelled, timed_out, neutral, skipped,
    ...) may have produced only some of its results, whatever the per-scanner steps say, so
    the scan is partial and the conclusion is named. A `run` whose conclusion cannot be read
    leaves the scan `unknown`: the record claims a run it does not describe. A scan-meta.json
    with no `run` (binary-scan and dast run locally) is judged by its steps alone.
    """
    if meta is None:
        return False, False, []
    if meta.get("outcome") == "not_scanned":
        # `dast run` records a target it did not scan (unreachable URL, ZAP missing) as a
        # scan directory holding only this scan-meta.json. Whatever its steps say, nothing
        # was scanned, and the reason is the one thing a reader needs.
        reason = meta.get("reason")
        why = f": {_text(reason)}" if isinstance(reason, str) and reason.strip() else ""
        return True, False, [f"the target was not scanned{why}"]
    if "run" not in meta:
        return False, False, []
    run = meta["run"]
    conclusion = run.get("conclusion") if isinstance(run, dict) else None
    if not (isinstance(conclusion, str) and conclusion.strip()):
        return False, True, ["the workflow run's conclusion is not recorded (`run.conclusion`)"]
    if conclusion != "success":
        run_id = run.get("run_id")
        which = f" (run {_text(run_id)})" if isinstance(run_id, (str, int)) and run_id else ""
        return (
            True,
            False,
            [f"the workflow run{which} concluded {_text(conclusion)}: findings may be partial"],
        )
    return False, False, []


def scan_key(
    result_file: Path, scans_dir: Path, resolve: Resolver = _real
) -> tuple[str, Path | None]:
    """The scan directory a result file belongs to, and its scan-meta.json if it has one.

    A scan directory is the directory holding scan-meta.json (the nearest one at or
    below `scans_dir`); a result file with no scan-meta.json above it is its own scan
    directory. Coverage is assessed once per scan directory, never per file. The key is
    the resolved directory, whatever form the paths were given in.
    """
    meta_path = find_meta(result_file.parent, scans_dir, resolve)
    return str(meta_path.parent if meta_path else resolve(result_file.parent)), meta_path


def scan_dirs(
    scans_dir: Path, result_files: Iterable[Path], resolve: Resolver = _real
) -> dict[str, Path | None]:
    """Every scan directory under `scans_dir`: key -> its scan-meta.json path (or None).

    Includes directories that hold a scan-meta.json but no result file the parser reads,
    so a scan that skipped everything is still reported. An empty or missing tree yields
    `scans_dir` itself, with no meta, so there is always something to report.
    """
    found: dict[str, Path | None] = {}
    if scans_dir.is_dir():
        for meta_path in sorted(scans_dir.rglob(META_NAME)):
            found[str(resolve(meta_path.parent))] = resolve(meta_path)
    for rf in result_files:
        key, meta_path = scan_key(rf, scans_dir, resolve)
        found.setdefault(key, meta_path)
    if not found:
        found[str(resolve(scans_dir))] = None
    return found


_NOTE_LIMIT = 20


#: The steps a mode plans: one tuple for every scan, or a function of the scan's own
#: scan-meta.json for a mode whose scanners differ per scan (`scan ingest`: the workflow
#: runs semgrep plus whatever `scan.extra_scanners` the client profile lists).
Planned = tuple[str, ...] | Callable[[dict | None], tuple[str, ...]]


def _bounded_notes(state: ScanRead) -> list[str]:
    """What a scan's files had to say, bounded, in the order that matters.

    Refusals (a file found and not read, and why) come first and are never cut: the unread
    limitation points at them ("named in another limitation"), and there are as many as
    there are result files, which is few. Then the other notes, then the "ignored" notes,
    sharing the `_NOTE_LIMIT` that bounds a pile of stray files. When the bound cuts, the
    ignored notes go first and the cut is counted, so 25 misnamed files never hide the
    reason a result could not be read.
    """
    refusals = [short(r) for r in state.refusals]
    others = [short(n) for n in state.notes]
    ignored = [short(n) for n in state.ignored]
    kept = others[:_NOTE_LIMIT]
    kept += ignored[: max(0, _NOTE_LIMIT - len(kept))]
    cut = len(others) + len(ignored) - len(kept)
    return refusals + kept + ([f"... and {cut} more notes"] if cut else [])


def planned_for(planned: Planned, meta: dict | None) -> tuple[str, ...]:
    """The planned steps of one scan directory."""
    return planned(meta) if callable(planned) else planned


def assess_all(
    dirs: dict[str, Path | None],
    planned: Planned,
    state_by_key: dict[str, ScanRead],
) -> dict[str, dict]:
    """Assess every scan directory: key -> {"scan_dir", "coverage", ..., "steps_read"}.

    The notes a scan's files produced are appended to its limitations (bounded), so they
    reach both the findings and the sidecar.
    """
    out: dict[str, dict] = {}
    for key, meta_path in dirs.items():
        state = state_by_key.get(key) or ScanRead()
        meta = load_meta(meta_path)
        planned_steps = planned_for(planned, meta)
        read = state.steps & set(planned_steps)
        report = assess(meta, planned_steps, read, state.degraded)
        report["limitations"] = report["limitations"] + _bounded_notes(state)
        out[key] = {
            "scan_dir": key,
            **report,
            "steps_read": [s for s in planned_steps if s in read],
        }
    return out


def split_by_scan_dir(
    scans_dir: Path,
    candidates: Iterable[Path],
    resolve: Resolver = _real,
    unplaceable: dict[Path, str] | None = None,
) -> tuple[list[Path], dict[str, list[Path]]]:
    """Keep only result files at the top level of their scan directory.

    A scan directory is the one holding scan-meta.json. A candidate in a subdirectory of
    it (an `old/checksec.json` left by an earlier run, a backup) is not part of that
    scan's result: it returns in the second value, keyed by the scan directory, so the
    parser can name it instead of silently folding it in. With no scan-meta.json above
    it a file is its own scan directory.

    Both sides of the comparison are resolved the same way (`resolve`), so a relative
    `scans_dir`, `.`, `..` segments, a trailing separator, a link or a differently-cased
    path decide exactly as the absolute path does. This never raises: a candidate it
    cannot place is not read and is not a crash either. It is NOT filed under `ignored`,
    which says "this file is not named or placed like a result": an internal failure there
    would read as a misnamed file. It goes into `unplaceable` (path -> the error), which the
    caller reports as a failure.
    """
    kept: list[Path] = []
    ignored: dict[str, list[Path]] = {}
    for path in candidates:
        try:
            key, _ = scan_key(path, scans_dir, resolve)
            top_level = _norm(key) == _norm(resolve(path.parent))
        except Exception as exc:  # noqa: BLE001 - discovery must degrade, never crash
            if unplaceable is not None:
                unplaceable[path] = f"{type(exc).__name__}: {short(exc)}"
                continue
            key, top_level = str(resolve(scans_dir)), False
        if top_level:
            kept.append(path)
        else:
            ignored.setdefault(key, []).append(path)
    return kept, ignored


def _display(path: Path, key: str) -> str:
    """`path` relative to the scan directory `key`, for a note; never raises."""
    try:
        return Path(os.path.relpath(_real(path), key)).as_posix()
    except (ValueError, OSError):
        return short(path)


def note_ignored(state_by_key: dict[str, ScanRead], ignored: dict[str, list[Path]]) -> None:
    """A result file left out because it is not at the top level of its scan directory."""
    for key, paths in ignored.items():
        state = state_by_key.setdefault(key, ScanRead())
        for path in paths:
            state.ignored.append(
                f"{_display(path, key)} was ignored: results are read only from {key} itself"
            )


#: Files a scan directory always holds that are never a mis-named result.
_NOT_RESULTS = frozenset({META_NAME, "coverage.json", "hash.json"})


def note_misnamed(
    state_by_key: dict[str, ScanRead],
    dirs: Iterable[str],
    exact: Iterable[str],
    hints: tuple[str, ...],
) -> None:
    """Name every file in a scan directory that looks like a result but is not named like one.

    Results are read only from the `exact` documented names. A `checksec-old.json`, a
    `strings-notes.txt` or a `Checksec.JSON` next to them is not read, and without this it
    would be ignored silently. `hints` are the name fragments that make a file look like
    a result for this mode.
    """
    exact = set(exact)
    listing = ", ".join(sorted(exact))
    for key in dirs:
        try:
            entries = sorted(Path(key).iterdir())
        except OSError:
            continue
        for entry in entries:
            low = entry.name.lower()
            try:
                is_file = entry.is_file()
            except OSError:
                continue
            if (
                not is_file
                or entry.name in exact
                or low in _NOT_RESULTS
                or not any(h in low for h in hints)
            ):
                continue
            state_by_key.setdefault(key, ScanRead()).ignored.append(
                f"{entry.name} was ignored: results are read only from {listing}"
            )


def collect(
    tag: str,
    scans_dir: Path,
    candidates: list[Path],
    planned: Planned,
    read_file: Callable[[Path, str], Read],
    exact: Iterable[str],
    hints: tuple[str, ...],
) -> tuple[list[dict], list[dict], int]:
    """Read every result file and assess every scan directory.

    Returns (findings stamped with their scan's coverage, one report per scan directory,
    the number of result files found). `read_file(path, target_name)` is the mode's own
    parser. Both parse_*.py scripts run through here, so discovery, notes and coverage
    are one implementation.
    """
    unplaceable: dict[Path, str] = {}
    scan_files, ignored = split_by_scan_dir(scans_dir, candidates, unplaceable=unplaceable)
    dirs = scan_dirs(scans_dir, scan_files)
    state_by_key: dict[str, ScanRead] = {}
    note_ignored(state_by_key, ignored)
    note_misnamed(state_by_key, dirs, exact, hints)
    for path, why in unplaceable.items():
        # An internal failure, not a misnamed file: name the file and the error, in the scan
        # directory the caller asked about (the one place a file with no scan has).
        key = str(_real(scans_dir))
        dirs.setdefault(key, None)
        print(f"  [error] Could not place {path.name}: {why}", file=sys.stderr)
        state_by_key.setdefault(key, ScanRead()).refusals.append(
            f"{path.name} could not be placed in a scan directory, so it was not read: {why}"
        )

    findings_by_key: dict[str, list[dict]] = {}
    for sf in scan_files:
        target_name = sf.parent.parent.name if sf.parent.name.count("-") == 2 else sf.parent.name
        key, _ = scan_key(sf, scans_dir)
        state = state_by_key.setdefault(key, ScanRead())
        print(f"[{tag}] Parsing {sf.name} → target={target_name}", file=sys.stderr)
        try:
            result = read_file(sf, target_name)
        except Exception as exc:  # noqa: BLE001 - an unreadable file leaves its step unread
            print(f"  [error] Failed to parse {sf.name}: {exc}", file=sys.stderr)
            state.refusals.append(f"{sf.name} could not be read: {short(exc)}")
            continue
        state.add(result)
        findings_by_key.setdefault(key, []).extend(result.findings)
        print(f"  → {len(result.findings)} findings", file=sys.stderr)

    reports = assess_all(dirs, planned, state_by_key)
    findings: list[dict] = []
    for key, found in findings_by_key.items():
        stamp(found, reports[key])
        findings.extend(found)
    return findings, list(reports.values()), len(scan_files)


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


def finding_coverage(finding: dict) -> tuple[str, list[str]]:
    """What a finding says about its own scan: (coverage, limitations), for a consumer.

    A finding that carries no coverage, a blank one, or a value outside the vocabulary
    reads `unknown`, never `complete`: a consumer that cannot tell must not say the scan
    was whole. Limitations are always a list of short strings; a finding with no usable
    coverage gets one limitation saying so, so an empty list never reads as "nothing
    was missed" next to `unknown`.
    """
    raw = finding.get("coverage")
    coverage = raw if isinstance(raw, str) and raw in (COMPLETE, PARTIAL, UNKNOWN) else UNKNOWN
    limits = finding.get("limitations")
    if isinstance(limits, str):
        limits = [limits]
    out = [short(x) for x in limits] if isinstance(limits, list) else []
    if coverage == UNKNOWN and raw != UNKNOWN and not out:
        out = ["scan coverage was not recorded for this finding"]
    return coverage, out


#: Weakest last: what one finding says when two scans disagree (see merge_duplicate).
_WEAKNESS = {COMPLETE: 0, UNKNOWN: 1, PARTIAL: 2}


def merge_duplicate(kept: dict, other: dict) -> None:
    """`kept` absorbs `other`, the same finding (same fingerprint) from another scan.

    A finding merged from scans with different coverage must not keep one scan's claim:
    it takes the weaker coverage (partial, then unknown, then complete), the union of both
    limitations, and says that another scan reported it. Two identically stamped findings,
    or two with no coverage at all, are left exactly as they were.
    """
    kept_cov, kept_lim = finding_coverage(kept)
    other_cov, other_lim = finding_coverage(other)
    extra = [x for x in other_lim if x not in kept_lim]
    if kept_cov == other_cov and not extra:
        return
    weaker = kept_cov if _WEAKNESS[kept_cov] >= _WEAKNESS[other_cov] else other_cov
    merged = kept_lim + extra
    merged.append(
        f"also reported by another scan with coverage {other_cov}; "
        f"the weaker coverage ({weaker}) is kept"
    )
    kept["coverage"] = weaker
    kept["limitations"] = merged


def deduplicate(findings: list[dict], severity_rank: dict[str, int]) -> list[dict]:
    """One finding per fingerprint: the highest severity wins, and the winner carries the
    weaker coverage of the scans that reported it (merge_duplicate). The three parse_*
    scripts share this; each passes its own severity ranking."""
    best: dict[str, dict] = {}
    for f in findings:
        fp = f["fingerprint"]
        if fp not in best:
            best[fp] = f
            continue
        current = best[fp]
        if severity_rank.get(f["severity"], 0) > severity_rank.get(current["severity"], 0):
            winner, loser = f, current
        else:
            winner, loser = current, f
        merge_duplicate(winner, loser)
        best[fp] = winner
    return list(best.values())


def unknown_report(scan_dir: str | None, limitation: str) -> dict:
    """A report for something that was never assessed against a run record."""
    return {
        "scan_dir": scan_dir,
        "coverage": UNKNOWN,
        "skipped_steps": [],
        "unread_steps": [],
        "degraded_steps": [],
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
