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
    replaced, a check name the doc does not list).
    """

    step: str | None
    findings: list
    degraded: list
    notes: list


class ScanRead:
    """Everything the parser learned about one scan directory, for assess_all()."""

    def __init__(self) -> None:
        self.steps: set[str] = set()
        self.degraded: dict[str, list[str]] = {}
        self.notes: list[str] = []

    def add(self, result: Read) -> None:
        if result.step is not None:
            self.steps.add(result.step)
            if result.degraded:
                self.degraded.setdefault(result.step, []).extend(result.degraded)
        self.notes.extend(result.notes)


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

_BAD_BYTES: list[int] = []


def _count_bad(exc: UnicodeError) -> tuple[str, int]:
    _BAD_BYTES.append(exc.end - exc.start)
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
    del _BAD_BYTES[:]
    text = data.decode(encoding, errors="scan_coverage_count")
    bad = sum(_BAD_BYTES)

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
            "degraded_steps": [],
            "limitations": [f"{why}; which steps ran is not known"],
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

    if skipped or unread or partly:
        coverage = PARTIAL
    elif unusable:
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


def assess_all(
    dirs: dict[str, Path | None],
    planned: tuple[str, ...],
    state_by_key: dict[str, ScanRead],
) -> dict[str, dict]:
    """Assess every scan directory: key -> {"scan_dir", "coverage", ..., "steps_read"}.

    The notes a scan's files produced are appended to its limitations (bounded), so they
    reach both the findings and the sidecar.
    """
    out: dict[str, dict] = {}
    for key, meta_path in dirs.items():
        state = state_by_key.get(key) or ScanRead()
        read = state.steps & set(planned)
        report = assess(load_meta(meta_path), planned, read, state.degraded)
        notes = [short(n) for n in state.notes]
        if len(notes) > _NOTE_LIMIT:
            notes = notes[:_NOTE_LIMIT] + [f"... and {len(notes) - _NOTE_LIMIT} more notes"]
        report["limitations"] = report["limitations"] + notes
        out[key] = {"scan_dir": key, **report, "steps_read": [s for s in planned if s in read]}
    return out


def split_by_scan_dir(
    scans_dir: Path, candidates: Iterable[Path], resolve: Resolver = _real
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
    cannot place is ignored and named, not a crash.
    """
    kept: list[Path] = []
    ignored: dict[str, list[Path]] = {}
    for path in candidates:
        try:
            key, _ = scan_key(path, scans_dir, resolve)
            top_level = _norm(key) == _norm(resolve(path.parent))
        except Exception:  # noqa: BLE001 - discovery must degrade, never crash
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
            state.notes.append(
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
            state_by_key.setdefault(key, ScanRead()).notes.append(
                f"{entry.name} was ignored: results are read only from {listing}"
            )


def collect(
    tag: str,
    scans_dir: Path,
    candidates: list[Path],
    planned: tuple[str, ...],
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
    scan_files, ignored = split_by_scan_dir(scans_dir, candidates)
    dirs = scan_dirs(scans_dir, scan_files)
    state_by_key: dict[str, ScanRead] = {}
    note_ignored(state_by_key, ignored)
    note_misnamed(state_by_key, dirs, exact, hints)

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
            state.notes.append(f"{sf.name} could not be read: {short(exc)}")
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
