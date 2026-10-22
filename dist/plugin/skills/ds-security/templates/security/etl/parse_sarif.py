"""
parse_sarif.py — SARIF/scanner output parser and normalizer.

Reads scan results from ~/.dream-studio/security/scans/{client}/
Supports: Semgrep SARIF, Bandit JSON, TruffleHog JSON, pip-audit JSON
Outputs: normalized flat findings list as JSON (stdout or file)

Every finding carries `coverage` (complete | partial | unknown) and `limitations` (see
scan_coverage.py). `complete` needs the run record in the scan directory's scan-meta.json
(`steps`: one entry per planned scanner, and `run.conclusion`) to say every planned scanner
ran and the workflow run concluded `success`, AND this parser to have read a result for
each scanner. A run that did not succeed, a scanner that failed or was skipped, a result
that is missing or unreadable (or one this parser has no reader for) makes the scan
partial and is named; a scan directory with no usable run record (a local-file ingest) is
unknown, never complete. `--coverage-output` writes the same facts per scan directory,
and writes them before any non-zero exit.

Usage:
    py -3.12 parse_sarif.py --client <name> [--scans-dir <path>] [--output <path>]
                            [--coverage-output <path>]
    py -3.12 parse_sarif.py --sample --client <name>
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# scan_coverage.py is a sibling of this script (shared with the other parse_* scripts).
_ETL_DIR = Path(__file__).resolve().parent
if str(_ETL_DIR) not in sys.path:
    sys.path.insert(0, str(_ETL_DIR))

import scan_coverage  # noqa: E402
from etl_home import home_dir  # noqa: E402

#: The scanners the security-scan workflow can run, as the step names of the run record
#: `scan ingest` writes into scan-meta.json (one per job: semgrep always, the rest from the
#: client profile's `scan.extra_scanners`). The steps a scan plans are the ones its own
#: scan-meta.json lists (`planned_steps`, plus any step it records), with semgrep as the
#: floor. A scanner whose output this parser has no reader for (npm-audit) is recorded as
#: ran and read as unread: its findings never reach the dataset, and that is said.
DEFAULT_STEPS = ("semgrep",)

# ── Severity ranking for deduplication (higher index = higher severity) ───────
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# ── OWASP / CWE maps for common Bandit test IDs ──────────────────────────────
BANDIT_CWE_MAP = {
    "B101": "CWE-617",
    "B102": "CWE-78",
    "B103": "CWE-732",
    "B104": "CWE-605",
    "B105": "CWE-259",
    "B106": "CWE-259",
    "B107": "CWE-259",
    "B108": "CWE-377",
    "B110": "CWE-390",
    "B112": "CWE-390",
    "B201": "CWE-78",
    "B301": "CWE-502",
    "B302": "CWE-502",
    "B303": "CWE-327",
    "B304": "CWE-327",
    "B305": "CWE-327",
    "B306": "CWE-377",
    "B307": "CWE-78",
    "B308": "CWE-79",
    "B310": "CWE-601",
    "B311": "CWE-330",
    "B312": "CWE-319",
    "B313": "CWE-611",
    "B314": "CWE-611",
    "B315": "CWE-611",
    "B316": "CWE-611",
    "B317": "CWE-611",
    "B318": "CWE-611",
    "B319": "CWE-611",
    "B320": "CWE-611",
    "B321": "CWE-321",
    "B322": "CWE-89",
    "B323": "CWE-295",
    "B324": "CWE-327",
    "B325": "CWE-330",
    "B401": "CWE-676",
    "B402": "CWE-676",
    "B403": "CWE-676",
    "B404": "CWE-78",
    "B405": "CWE-676",
    "B406": "CWE-676",
    "B407": "CWE-676",
    "B408": "CWE-676",
    "B409": "CWE-676",
    "B410": "CWE-676",
    "B411": "CWE-676",
    "B412": "CWE-676",
    "B413": "CWE-676",
    "B501": "CWE-295",
    "B502": "CWE-295",
    "B503": "CWE-295",
    "B504": "CWE-295",
    "B505": "CWE-326",
    "B506": "CWE-20",
    "B507": "CWE-295",
    "B601": "CWE-78",
    "B602": "CWE-78",
    "B603": "CWE-78",
    "B604": "CWE-78",
    "B605": "CWE-78",
    "B606": "CWE-78",
    "B607": "CWE-78",
    "B608": "CWE-89",
    "B609": "CWE-78",
    "B610": "CWE-89",
    "B611": "CWE-89",
    "B701": "CWE-79",
    "B702": "CWE-79",
    "B703": "CWE-79",
}

BANDIT_OWASP_MAP = {
    "B105": "A07:2021",
    "B106": "A07:2021",
    "B107": "A07:2021",
    "B301": "A08:2021",
    "B302": "A08:2021",
    "B303": "A02:2021",
    "B304": "A02:2021",
    "B305": "A02:2021",
    "B307": "A03:2021",
    "B322": "A03:2021",
    "B608": "A03:2021",
    "B610": "A03:2021",
    "B611": "A03:2021",
    "B308": "A03:2021",
    "B701": "A03:2021",
    "B702": "A03:2021",
    "B501": "A02:2021",
    "B502": "A02:2021",
    "B503": "A02:2021",
    "B504": "A02:2021",
    "B505": "A02:2021",
    "B507": "A02:2021",
    "B601": "A03:2021",
    "B602": "A03:2021",
    "B603": "A03:2021",
    "B604": "A03:2021",
    "B605": "A03:2021",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fingerprint(repo: str, file: str, line: int | None, rule_id: str) -> str:
    raw = f"{repo}|{file}|{line}|{rule_id}"
    return "sha256-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_severity(raw: str) -> str:
    mapping = {
        "error": "high",
        "warning": "medium",
        "note": "low",
        "none": "info",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "critical": "critical",
        "info": "info",
        # Bandit SEVERITY variants
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
    }
    return mapping.get(raw, "low")


def _repo_from_path(scan_file_stem: str) -> str:
    """Infer repo name from scan filename (e.g. vendor-portal-semgrep.sarif)."""
    # Strip known scanner suffixes
    for suffix in ("-semgrep", "-bandit", "-trufflehog", "-pip-audit", "-pipaudit"):
        if scan_file_stem.endswith(suffix):
            return scan_file_stem[: -len(suffix)]
    return scan_file_stem


# ── Parser: Semgrep SARIF ─────────────────────────────────────────────────────


def parse_semgrep_sarif(data: dict, repo: str) -> list[dict]:
    findings = []
    runs = data.get("runs", [])
    # a `runs` that is not a list of objects holds no run; read_result_file says so
    for run in [r for r in (runs if isinstance(runs, list) else []) if isinstance(r, dict)]:
        rules_meta = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            rid = rule.get("id", "")
            props = rule.get("properties", {})
            tags = props.get("tags", [])
            cwe = next((t for t in tags if t.startswith("CWE-")), None)
            owasp = next((t for t in tags if t.startswith("A") and ":20" in t), None)
            rules_meta[rid] = {
                "cwe": cwe or props.get("cwe", ""),
                "owasp": owasp or props.get("owasp", ""),
                "name": rule.get("name", rid),
            }

        for result in run.get("results", []):
            rule_id = result.get("ruleId", "unknown")
            raw_level = result.get("level", "warning")
            severity = _normalize_severity(raw_level)

            location = {}
            locs = result.get("locations", [])
            if locs:
                phys = locs[0].get("physicalLocation", {})
                uri = phys.get("artifactLocation", {}).get("uri", "")
                line = phys.get("region", {}).get("startLine")
                location = {"file": uri, "line": line}

            msg = result.get("message", {})
            message = msg.get("text", "") if isinstance(msg, dict) else str(msg)

            meta = rules_meta.get(rule_id, {})
            fp = _fingerprint(repo, location.get("file", ""), location.get("line"), rule_id)

            findings.append(
                {
                    "id": fp,
                    "repo": repo,
                    "file": location.get("file", ""),
                    "line": location.get("line"),
                    "rule_id": rule_id,
                    "severity": severity,
                    "message": message,
                    "cwe": meta.get("cwe", ""),
                    "owasp": meta.get("owasp", ""),
                    "scanner": "semgrep",
                    "raw_severity": raw_level,
                    "fingerprint": fp,
                    "target_type": "repo",
                    "target_name": "",
                    "url": "",
                    "http_method": "",
                    "binary_hash": "",
                }
            )
    return findings


# ── Parser: Bandit JSON ───────────────────────────────────────────────────────


def parse_bandit(data: dict, repo: str) -> list[dict]:
    findings = []
    results = data.get("results", [])
    for r in results:
        rule_id = r.get("test_id", "unknown")
        raw_sev = r.get("issue_severity", "LOW")
        severity = _normalize_severity(raw_sev)
        filename = r.get("filename", "")
        line = r.get("line_number")
        message = r.get("issue_text", "")
        fp = _fingerprint(repo, filename, line, rule_id)
        findings.append(
            {
                "id": fp,
                "repo": repo,
                "file": filename,
                "line": line,
                "rule_id": rule_id,
                "severity": severity,
                "message": message,
                "cwe": BANDIT_CWE_MAP.get(rule_id, ""),
                "owasp": BANDIT_OWASP_MAP.get(rule_id, ""),
                "scanner": "bandit",
                "raw_severity": raw_sev,
                "fingerprint": fp,
                "target_type": "repo",
                "target_name": "",
                "url": "",
                "http_method": "",
                "binary_hash": "",
            }
        )
    return findings


# ── Parser: TruffleHog JSON ───────────────────────────────────────────────────


def _trufflehog_location(result: dict) -> tuple[str, int | None]:
    """(file, line) from a trufflehog result's SourceMetadata, whatever the source type
    (Git, Filesystem, Github, ...): the first source object that names a file."""
    meta = result.get("SourceMetadata")
    data = meta.get("Data") if isinstance(meta, dict) else None
    if not isinstance(data, dict):
        return "", None
    for source in data.values():
        if isinstance(source, dict) and isinstance(source.get("file"), str):
            line = source.get("line")
            return source["file"], (
                line if isinstance(line, int) and not isinstance(line, bool) else None
            )
    return "", None


def parse_trufflehog(data_list: list, repo: str) -> list[dict]:
    """Findings from trufflehog results. A secret is high severity.

    A finding carries the detector name, the file, the line and whether trufflehog verified the
    secret live, and NOTHING of the secret: `Raw`, `RawV2` and the partly masked `Redacted`
    are never read, and neither is the commit author. The old finding put `Raw[:80]` in its
    message, which reached the findings JSON, the CSV and the dashboard.
    """
    findings = []
    if isinstance(data_list, dict):
        data_list = data_list.get("results", [data_list])
    for r in data_list if isinstance(data_list, list) else []:
        if not isinstance(r, dict):
            continue
        detector = r.get("DetectorName")
        detector = (
            scan_coverage.short(detector) if isinstance(detector, str) and detector else "secret"
        )
        filename, line = _trufflehog_location(r)
        verified = r.get("Verified") is True
        rule_id = f"TH-{detector}"
        fp = _fingerprint(repo, filename, line, rule_id)
        state = "verified by trufflehog" if verified else "unverified"
        findings.append(
            {
                "id": fp,
                "repo": repo,
                "file": scan_coverage.short(filename),
                "line": line,
                "rule_id": rule_id,
                "severity": "high",
                "message": f"Secret detected by {detector} ({state}; value redacted)",
                "cwe": "CWE-312",
                "owasp": "A02:2021",
                "scanner": "trufflehog",
                "raw_severity": "HIGH",
                "fingerprint": fp,
                "target_type": "repo",
                "target_name": "",
                "url": "",
                "http_method": "",
                "binary_hash": "",
            }
        )
    return findings


#: How many failing lines a limitation numbers; the rest are counted.
_NAMED_LINES = 5


def jsonl_lines(text: str) -> list[str]:
    """The lines of a JSON Lines text: split on LF only, each stripped of spaces, tabs and CR.

    Not str.splitlines(), which also splits on U+0085, U+2028, U+2029, form feed and the rest:
    a result whose value holds one (JSON allows it raw) became two unreadable lines. A line of
    nothing but such a character is a junk line, not a blank one. Blank lines read as ''.
    """
    return [line.strip(" \t\r") for line in text.split("\n")]


def read_trufflehog_lines(text: str, name: str) -> tuple[list[dict], list[str], list[str]]:
    """(findings, degraded, notes) from trufflehog JSON Lines (`--json`: one result per line).

    The file may also hold trufflehog's own log lines (the old workflow merged stderr into it);
    those are set aside with a note. A line that is neither a result nor a log line is skipped
    and numbered in `degraded`, never quoted: it may be the secret.
    """
    results: list[dict] = []
    logs = 0
    bad: list[int] = []
    for number, line in enumerate(jsonl_lines(text), 1):
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            bad.append(number)
            continue
        if isinstance(obj, dict) and ("DetectorName" in obj or "SourceMetadata" in obj):
            results.append(obj)
        elif isinstance(obj, dict) and "level" in obj and "msg" in obj:
            logs += 1
        else:
            bad.append(number)
    degraded: list[str] = []
    notes: list[str] = []
    if bad:
        shown = ", ".join(str(n) for n in bad[:_NAMED_LINES])
        more = ", ..." if len(bad) > _NAMED_LINES else ""
        degraded.append(
            f"{len(bad)} line(s) of {name} could not be read as trufflehog results and were "
            f"skipped (lines {shown}{more})"
        )
    if logs:
        notes.append(f"{logs} trufflehog log line(s) in {name} were ignored: they are not results")
    return parse_trufflehog(results, ""), degraded, notes


# ── Parser: pip-audit JSON ────────────────────────────────────────────────────


def parse_pip_audit(data_list: list, repo: str) -> list[dict]:
    findings = []
    if isinstance(data_list, dict):
        data_list = data_list.get("dependencies", [])
    for pkg in data_list:
        name = pkg.get("name", "unknown")
        version = pkg.get("version", "?")
        for vuln in pkg.get("vulns", []):
            vid = vuln.get("id", "UNKNOWN")
            desc = vuln.get("description", "")
            fixes = vuln.get("fix_versions", [])
            fix_str = f" Fix: upgrade to {', '.join(fixes)}." if fixes else ""
            rule_id = f"PA-{vid}"
            # Severity heuristic from CVSS score in id prefix
            if vid.startswith("GHSA") or vid.startswith("CVE"):
                sev = "high"
            else:
                sev = "medium"
            fp = _fingerprint(repo, f"requirements/{name}", None, rule_id)
            findings.append(
                {
                    "id": fp,
                    "repo": repo,
                    "file": f"requirements.txt ({name}=={version})",
                    "line": None,
                    "rule_id": rule_id,
                    "severity": sev,
                    "message": f"{name}=={version} has known vulnerability {vid}.{fix_str} {desc}".strip(),
                    "cwe": "CWE-1395",
                    "owasp": "A06:2021",
                    "scanner": "pip-audit",
                    "raw_severity": sev,
                    "fingerprint": fp,
                    "target_type": "repo",
                    "target_name": "",
                    "url": "",
                    "http_method": "",
                    "binary_hash": "",
                }
            )
    return findings


# ── Auto-detect scanner from file content ─────────────────────────────────────


def detect_step(data: object) -> str | None:
    """Which scanner a parsed result file is the output of; None if it is none we read.

    Decided by content, not file name (the workflow's artifacts keep the scanner's own
    names: semgrep-results.sarif, bandit-results.json, ...).
    """
    if isinstance(data, dict):
        schema = data.get("$schema", "")
        runs = data.get("runs")
        first_run = runs[0] if isinstance(runs, list) and runs else None
        if (isinstance(schema, str) and "sarif" in schema.lower()) or (
            isinstance(first_run, dict) and "results" in first_run
        ):
            return "semgrep"

        results = data.get("results")
        if isinstance(results, list):
            sample = results[0] if results and isinstance(results[0], dict) else {}
            # Bandit: results with 'test_id' or 'issue_severity'. A run that found nothing
            # has no result to look at, but still carries bandit's own envelope.
            if "test_id" in sample or "issue_severity" in sample:
                return "bandit"
            if not results and "metrics" in data and "generated_at" in data:
                return "bandit"
            # TruffleHog dict wrapper
            if "DetectorName" in sample or "SourceMetadata" in sample:
                return "trufflehog"

        # pip-audit dict wrapper
        if isinstance(data.get("dependencies"), list):
            return "pip-audit"

    if isinstance(data, list):
        sample = data[0] if data and isinstance(data[0], dict) else {}
        # pip-audit: top-level list of {name, version, vulns}
        if "vulns" in sample:
            return "pip-audit"
        # TruffleHog top-level list
        if "DetectorName" in sample or "SourceMetadata" in sample:
            return "trufflehog"
    return None


def detect_and_parse(data: object, filename: str, repo: str) -> list[dict]:
    step = detect_step(data)
    if step == "semgrep":
        return parse_semgrep_sarif(data, repo)
    if step == "bandit":
        return parse_bandit(data, repo)
    if step == "trufflehog":
        return parse_trufflehog(data["results"] if isinstance(data, dict) else data, repo)
    if step == "pip-audit":
        return parse_pip_audit(data["dependencies"] if isinstance(data, dict) else data, repo)
    print(f"  [warn] Could not detect scanner format for {filename}", file=sys.stderr)
    return []


# ── Reading a scan directory, with coverage ──────────────────────────────────


#: Files a scan directory holds that are never a scanner's result.
NOT_RESULTS = frozenset({scan_coverage.META_NAME, "coverage.json", "hash.json"})


def is_result_file(path: Path) -> bool:
    """Candidate result files: .json / .sarif / .jsonl files, never scan-meta.json and its
    siblings. (.jsonl: trufflehog's JSON Lines results.)"""
    return (
        path.suffix in (".json", ".sarif", ".jsonl")
        and path.is_file()
        and path.name not in NOT_RESULTS
    )


def planned_steps(meta: dict | None) -> tuple[str, ...]:
    """The scanners one scan planned, from its scan-meta.json (see DEFAULT_STEPS)."""
    names: list[str] = list(DEFAULT_STEPS)
    if meta is not None:
        listed = meta.get("planned_steps")
        recorded = meta.get("steps")
        for source in (listed, recorded):
            if not isinstance(source, list):
                continue
            for item in source:
                name = item.get("step") if isinstance(item, dict) else item
                if isinstance(name, str) and name and name not in names:
                    names.append(name)
    return tuple(names)


#: File-name fragments that say which scanner a result belongs to, for a file too corrupt to
#: tell by its content. `pip-audit` and `pipaudit` are the two spellings the workflow's
#: artifacts and the older doc used.
SCANNER_NAME_HINTS = (
    ("semgrep", "semgrep"),
    ("bandit", "bandit"),
    ("trufflehog", "trufflehog"),
    ("pip-audit", "pip-audit"),
    ("pipaudit", "pip-audit"),
    ("npm-audit", "npm-audit"),
)


def scanner_from_name(name: str) -> str | None:
    """The scanner a file name points at, or None. Names are free-form (the workflow keeps
    each scanner's own), so this is a hint used only when the content cannot be read."""
    low = name.lower()
    return next((step for hint, step in SCANNER_NAME_HINTS if hint in low), None)


def sarif_degradation(raw: object) -> str | None:
    """Why a SARIF document is not evidence that semgrep ran to the end; None when it is.

    semgrep always writes one run, with a `results` list (empty when it found nothing). A
    document with no runs, or runs with no results list, is a schema stub or a truncated
    write: it must not read as a clean complete scan with zero findings.
    """
    runs = raw.get("runs") if isinstance(raw, dict) else None
    if not isinstance(runs, list) or not runs:
        return "no runs in the SARIF: it holds no run, so it does not show the scan completed"
    if not any(isinstance(r, dict) and isinstance(r.get("results"), list) for r in runs):
        return "no results list in any run of the SARIF: it does not show the scan completed"
    return None


def _unreadable(path: Path, exc: Exception) -> scan_coverage.Read:
    """A file that cannot be read: named, and when its name says which scanner it belongs to
    that scanner is degraded (partial). A name that says nothing re-raises, so the caller
    records the refusal."""
    step = scanner_from_name(path.name)
    if step is None:
        raise exc
    reason = f"{path.name} could not be read ({scan_coverage.short(exc)})"
    return scan_coverage.Read(
        None,
        [],
        [],
        [],
        [f"{path.name} could not be read: {scan_coverage.short(exc)}"],
        ((step, f"{reason}, so {step}'s output may be incomplete"),),
    )


def _read_trufflehog_file(path, decoded, hinted, repo) -> scan_coverage.Read:
    findings, degraded, notes = read_trufflehog_lines(decoded.text, path.name)
    for finding in findings:  # the lines were parsed without a repo; stamp it now
        finding["repo"] = repo
        finding["fingerprint"] = finding["id"] = _fingerprint(
            repo, finding["file"], finding["line"], finding["rule_id"]
        )
    nonblank = any(jsonl_lines(decoded.text))
    is_trufflehog = (
        bool(findings)
        or any("log line(s)" in n for n in notes)
        or (hinted == "trufflehog" and (not nonblank or degraded))
    )
    all_notes = list(decoded.notes) + notes
    if not is_trufflehog:
        refusal = f"{path.name} is not the output of a scanner this parser reads"
        return scan_coverage.Read(None, [], [], all_notes, [refusal])
    return scan_coverage.Read("trufflehog", findings, list(decoded.degraded) + degraded, all_notes)


def read_result_file(path: Path, target_name: str) -> scan_coverage.Read:
    """Parse one scanner result into a scan_coverage.Read.

    The scanner (the planned step the file is the output of) is decided by content. A file
    that is JSON but no scanner's output reads as no step and is named. One that cannot be
    read is named too, and when its name says which scanner it belongs to that scanner is
    degraded (partial): a corrupt second semgrep file must not hide behind a good first.
    """
    try:
        decoded = scan_coverage.decode_text(path.read_bytes(), path.name)
    except (OSError, ValueError, RecursionError) as exc:
        return _unreadable(path, exc)
    hinted = scanner_from_name(path.name)
    raw: object = None
    is_document = False
    if path.suffix.lower() != ".jsonl":
        try:
            raw = json.loads(decoded.text)
            is_document = True
        except (ValueError, RecursionError) as exc:
            if hinted != "trufflehog":
                return _unreadable(path, exc)
    if not is_document:
        # JSON Lines: trufflehog's `--json` output, or the merged stream the old workflow wrote
        # into trufflehog-results.json (not a document, so read by its name).
        return _read_trufflehog_file(path, decoded, hinted, repo_for(path, target_name))
    step = detect_step(raw)
    notes = list(decoded.notes)
    if step is None:
        refusal = f"{path.name} is not the output of a scanner this parser reads"
        return scan_coverage.Read(None, [], [], notes, [refusal])
    degraded = list(decoded.degraded)
    if step == "semgrep":
        problem = sarif_degradation(raw)
        if problem:
            degraded.append(f"{path.name}: {problem}")
    return scan_coverage.Read(
        step, detect_and_parse(raw, path.name, repo_for(path, target_name)), degraded, notes
    )


def repo_for(path: Path, target_name: str) -> str:
    """The repo a result belongs to: the file name's scanner-suffix prefix when it has one
    (`vendor-portal-semgrep.sarif`), else the scan directory's repo (`{repo}/{date}/`)."""
    named = _repo_from_path(path.stem)
    return named if named != path.stem else target_name


# ── Deduplication ─────────────────────────────────────────────────────────────


def deduplicate(findings: list[dict]) -> list[dict]:
    """Keep one finding per fingerprint; prefer highest severity. Scans that disagree about
    coverage leave the weaker one on the merged finding (see scan_coverage.deduplicate)."""
    return scan_coverage.deduplicate(findings, SEVERITY_RANK)


# ── Sample data generator ─────────────────────────────────────────────────────


def generate_sample() -> list[dict]:
    """Generate 8 synthetic findings across 3 repos for pipeline testing."""
    raw_findings = [
        {
            "repo": "vendor-portal",
            "file": "app/auth.py",
            "line": 34,
            "rule_id": "python.django.security.injection.tainted-sql-string.tainted-sql-string",
            "severity": "high",
            "message": "SQL injection via string concatenation in auth query",
            "cwe": "CWE-89",
            "owasp": "A03:2021",
            "scanner": "semgrep",
            "raw_severity": "error",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "vendor-portal",
            "file": "app/views/pricing.py",
            "line": 112,
            "rule_id": "B608",
            "severity": "high",
            "message": "Possible SQL injection via string-based query construction",
            "cwe": "CWE-89",
            "owasp": "A03:2021",
            "scanner": "bandit",
            "raw_severity": "HIGH",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "vendor-portal",
            "file": "app/utils/crypto.py",
            "line": 8,
            "rule_id": "B303",
            "severity": "medium",
            "message": "Use of MD5 or SHA1 hashing functions considered weak",
            "cwe": "CWE-327",
            "owasp": "A02:2021",
            "scanner": "bandit",
            "raw_severity": "MEDIUM",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "vendor-portal",
            "file": "requirements.txt (requests==2.25.1)",
            "line": None,
            "rule_id": "PA-CVE-2023-32681",
            "severity": "high",
            "message": "requests==2.25.1 has known vulnerability CVE-2023-32681. Fix: upgrade to 2.31.0.",
            "cwe": "CWE-1395",
            "owasp": "A06:2021",
            "scanner": "pip-audit",
            "raw_severity": "high",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "pricing-api",
            "file": "src/db/queries.py",
            "line": 55,
            "rule_id": "python.lang.security.use-defused-xml.use-defused-xml",
            "severity": "medium",
            "message": "Unsafe XML parsing — use defusedxml to prevent XXE",
            "cwe": "CWE-611",
            "owasp": "A05:2021",
            "scanner": "semgrep",
            "raw_severity": "warning",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "pricing-api",
            "file": "src/config.py",
            "line": 3,
            "rule_id": "TH-AWSAccessToken",
            "severity": "critical",
            "message": "Secret detected by AWSAccessToken: 'AKIA...' (truncated)",
            "cwe": "CWE-312",
            "owasp": "A02:2021",
            "scanner": "trufflehog",
            "raw_severity": "CRITICAL",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "planogram-service",
            "file": "planogram/render.py",
            "line": 78,
            "rule_id": "B301",
            "severity": "high",
            "message": "Pickle usage detected — arbitrary code execution risk",
            "cwe": "CWE-502",
            "owasp": "A08:2021",
            "scanner": "bandit",
            "raw_severity": "HIGH",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
        {
            "repo": "planogram-service",
            "file": "requirements.txt (pillow==9.0.0)",
            "line": None,
            "rule_id": "PA-GHSA-56pw-mpj4-fq4w",
            "severity": "high",
            "message": "pillow==9.0.0 has known vulnerability GHSA-56pw-mpj4-fq4w. Fix: upgrade to 9.3.0.",
            "cwe": "CWE-1395",
            "owasp": "A06:2021",
            "scanner": "pip-audit",
            "raw_severity": "high",
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        },
    ]

    findings = []
    for r in raw_findings:
        fp = _fingerprint(r["repo"], r["file"], r["line"], r["rule_id"])
        findings.append(
            {
                "id": fp,
                "repo": r["repo"],
                "file": r["file"],
                "line": r["line"],
                "rule_id": r["rule_id"],
                "severity": r["severity"],
                "message": r["message"],
                "cwe": r["cwe"],
                "owasp": r["owasp"],
                "scanner": r["scanner"],
                "raw_severity": r["raw_severity"],
                "fingerprint": fp,
                "target_type": r["target_type"],
                "target_name": r["target_name"],
                "url": r["url"],
                "http_method": r["http_method"],
                "binary_hash": r["binary_hash"],
            }
        )
    return findings


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize security scanner outputs (SARIF, Bandit, TruffleHog, pip-audit)"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. acme-corp)")
    parser.add_argument(
        "--scans-dir",
        help="Directory containing scan files. Default: ~/.dream-studio/security/scans/{client}/",
    )
    parser.add_argument("--output", help="Output file path. Default: stdout")
    parser.add_argument(
        "--coverage-output",
        help="Write per-scan coverage (complete|partial|unknown, failed steps, the workflow "
        "run's conclusion, limitations) to this JSON file. Needed to see coverage on a scan "
        "that produced no findings.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Generate synthetic sample findings for pipeline testing",
    )
    args = parser.parse_args()

    scan_reports: list[dict] = []

    if args.sample:
        findings = generate_sample()
        sample = scan_coverage.unknown_report(None, "synthetic sample data; no scan was run")
        scan_coverage.stamp(findings, sample)
        scan_reports.append(sample)
        print(f"[parse_sarif] Generated {len(findings)} sample findings", file=sys.stderr)
        scan_coverage.report("parse_sarif", scan_reports, args.coverage_output)
    else:
        scans_dir = (
            Path(args.scans_dir)
            if args.scans_dir
            else home_dir() / "security" / "scans" / args.client
        ).resolve()
        if not scans_dir.exists():
            scan_reports.append(
                scan_coverage.unknown_report(
                    str(scans_dir), f"scans directory not found: {scans_dir}"
                )
            )
            print(f"[parse_sarif] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            scan_coverage.report("parse_sarif", scan_reports, args.coverage_output)
            sys.exit(1)

        try:
            candidates = sorted(f for f in scans_dir.iterdir() if is_result_file(f))
            all_findings, reports, n_files = scan_coverage.collect(
                "parse_sarif",
                scans_dir,
                candidates,
                planned_steps,
                read_result_file,
                (),
                (),
            )
        except Exception as exc:  # noqa: BLE001 - never exit without the coverage sidecar
            print(f"[parse_sarif] ERROR: reading results failed: {exc}", file=sys.stderr)
            scan_reports.append(
                scan_coverage.unknown_report(
                    str(scans_dir),
                    f"unexpected failure while reading results: {scan_coverage.short(exc)}",
                )
            )
            scan_coverage.report("parse_sarif", scan_reports, args.coverage_output)
            sys.exit(1)
        scan_reports.extend(reports)

        if not n_files:
            print(
                f"[parse_sarif] No .json/.sarif/.jsonl files found in {scans_dir}. parse_sarif "
                "reads the result files directly in --scans-dir and does not walk the client "
                "tree: pass --scans-dir the scan directory (scans/{client}/{repo}/{date}).",
                file=sys.stderr,
            )
            scan_coverage.report("parse_sarif", scan_reports, args.coverage_output)
            sys.exit(1)

        findings = deduplicate(all_findings)
        print(
            f"[parse_sarif] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )
        scan_coverage.report("parse_sarif", scan_reports, args.coverage_output)

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_sarif] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
