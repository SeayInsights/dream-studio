"""
parse_binary.py — Binary analysis result parser and normalizer.

Reads binary analysis results from ~/.dream-studio/security/scans/{client}/
Supports: checksec JSON, YARA JSON, strings analysis output (strings-findings.txt as
          examples.md A6 writes it, or a {"findings": [...]} JSON), and PE/ELF header
          analysis (header-analysis.json, examples.md A7)
Outputs: normalized flat findings list as JSON (stdout or file)

Every finding carries `coverage` (complete | partial | unknown) and `limitations`
(see scan_coverage.py). `complete` needs the run record in the scan's scan-meta.json to
say every planned step ran AND this parser to have read a result for each of them: a
step that was skipped, or recorded as ran but whose output is missing, empty,
unparseable or of a kind not read here, makes the scan partial and is named; a scan
directory with no usable run record is unknown, never complete. The findings are flat
dicts with no schema behind them, so no migration is involved. A scan with zero findings
carries nothing on a finding, so `--coverage-output` writes the same facts per scan
directory, and writes them before any non-zero exit.

Usage:
    py -3.12 parse_binary.py --client <name> [--scans-dir <path>] [--output <path>]
                             [--coverage-output <path>]
    py -3.12 parse_binary.py --sample --client <name>
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

# This script runs in place from the repo (`py -3.12 templates/security/etl/...py`,
# see templates/security/README.md), which puts its own directory on sys.path, not
# the repo root -- the resolver import below needs a manual add.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# scan_coverage.py is a sibling of this script (shared with the other parse_* scripts).
_ETL_DIR = Path(__file__).resolve().parent
if str(_ETL_DIR) not in sys.path:
    sys.path.insert(0, str(_ETL_DIR))

import scan_coverage  # noqa: E402
from core.config.paths import home_dir  # noqa: E402

#: Every step `binary-scan analyze` runs when all its tooling is present
#: (examples.md A4-A7). Coverage is complete only when each one is recorded as run
#: AND this parser read a result for it: checksec.json, yara-matches.json,
#: strings-findings.txt (or .json) and header-analysis.json.
PLANNED_STEPS = ("checksec", "yara", "strings", "header_analysis")


SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

CHECKSEC_CHECK_META = {
    "nx": {
        "severity": "high",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "NX (Non-Executable Stack) not enabled — stack buffer overflows can execute code",
    },
    "pie": {
        "severity": "high",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "PIE (Position Independent Executable) not enabled — ASLR ineffective",
    },
    "relro": {
        "severity": "medium",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "Full RELRO not enabled — GOT overwrite attacks possible",
    },
    "canary": {
        "severity": "high",
        "cwe": "CWE-121",
        "owasp": "A06:2021",
        "message": "Stack canaries not enabled — stack buffer overflow protection missing",
    },
    "fortify": {
        "severity": "medium",
        "cwe": "CWE-120",
        "owasp": "A06:2021",
        "message": "FORTIFY_SOURCE not enabled — no bounds checking on libc functions",
    },
    "runpath": {
        "severity": "medium",
        "cwe": "CWE-426",
        "owasp": "A06:2021",
        "message": "RUNPATH/RPATH set to writable directory — DLL/shared library hijacking possible",
    },
    "dep": {
        "severity": "high",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "DEP (Data Execution Prevention) not enabled",
    },
    "aslr": {
        "severity": "high",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "ASLR not enabled — memory layout predictable",
    },
    "cfg": {
        "severity": "medium",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "Control Flow Guard (CFG) not enabled",
    },
    "safeseh": {
        "severity": "medium",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "SafeSEH not enabled — SEH overwrite attacks possible",
    },
    "authenticode": {
        "severity": "high",
        "cwe": "CWE-345",
        "owasp": "A08:2021",
        "message": "Binary not signed with Authenticode — integrity cannot be verified",
    },
    "high_entropy_va": {
        "severity": "low",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "High Entropy VA not enabled — 64-bit ASLR less effective",
    },
    "code_sign": {
        "severity": "high",
        "cwe": "CWE-345",
        "owasp": "A08:2021",
        "message": "Code signature missing or invalid",
    },
    "hardened_runtime": {
        "severity": "medium",
        "cwe": "CWE-693",
        "owasp": "A05:2021",
        "message": "Hardened runtime not enabled",
    },
    "arc": {
        "severity": "low",
        "cwe": "CWE-416",
        "owasp": "A06:2021",
        "message": "ARC (Automatic Reference Counting) not enabled — use-after-free risk",
    },
}


def _fingerprint(target: str, check: str, rule_id: str) -> str:
    raw = f"{target}|{check}|{rule_id}"
    return "sha256-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_severity(raw: str) -> str:
    mapping = {
        "high": "high",
        "medium": "medium",
        "low": "low",
        "critical": "critical",
        "info": "info",
    }
    return mapping.get(raw.lower() if raw else "low", "low")


# ── Parser: checksec JSON ────────────────────────────────────────────────────


def parse_checksec_json(data: dict, target_name: str, binary_hash: str = "") -> list[dict]:
    findings = []

    file_results = None
    if "file" in data and isinstance(data["file"], dict):
        file_results = data
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, dict) and any(
                k in val for k in ("nx", "pie", "relro", "canary", "dep", "aslr")
            ):
                file_results = {key: val}
                break

    if file_results is None:
        if "error" in data:
            return []
        file_results = data

    for binary_name, checks in file_results.items():
        if not isinstance(checks, dict):
            continue

        for check_name, check_value in checks.items():
            check_name_lower = check_name.lower().replace("_", "").replace("-", "")

            is_fail = False
            if isinstance(check_value, bool):
                is_fail = not check_value
            elif isinstance(check_value, str):
                fail_values = {"no", "false", "disabled", "partial", "none", "not found"}
                is_fail = check_value.lower().strip() in fail_values
                if check_name_lower == "relro" and check_value.lower() == "partial":
                    is_fail = True

            if not is_fail:
                continue

            meta = CHECKSEC_CHECK_META.get(
                check_name_lower, CHECKSEC_CHECK_META.get(check_name.lower(), {})
            )
            severity = meta.get("severity", "medium")
            cwe = meta.get("cwe", "CWE-119")
            owasp = meta.get("owasp", "A06:2021")
            message = meta.get(
                "message", f"Hardening check '{check_name}' failed (value: {check_value})"
            )

            rule_id = f"BIN-chk-{check_name.lower()}"
            fp = _fingerprint(target_name, binary_name + check_name, rule_id)

            findings.append(
                {
                    "id": fp,
                    "repo": target_name,
                    "file": binary_name,
                    "line": None,
                    "rule_id": rule_id,
                    "severity": severity,
                    "message": message,
                    "cwe": cwe,
                    "owasp": owasp,
                    "scanner": "checksec",
                    "raw_severity": severity,
                    "fingerprint": fp,
                    "target_type": "binary",
                    "target_name": target_name,
                    "url": "",
                    "http_method": "",
                    "binary_hash": binary_hash,
                    "hardening_check": check_name,
                    "binary_section": "",
                    "yara_rule": "",
                }
            )

    return findings


# ── Parser: YARA JSON ────────────────────────────────────────────────────────


def parse_yara_json(data: object, target_name: str, binary_hash: str = "") -> list[dict]:
    findings = []

    matches = []
    if isinstance(data, dict):
        matches = data.get("matches", [])
        if not matches and "rules" in data:
            matches = data["rules"]
    elif isinstance(data, list):
        matches = data

    for raw_match in matches:
        if isinstance(raw_match, str):
            parts = raw_match.split(" ", 1)
            rule_name = parts[0] if parts else raw_match
            match: dict = {"rule": rule_name}
        else:
            match = raw_match

        rule_name = match.get("rule", "unknown")
        meta = match.get("meta", {})
        severity = _normalize_severity(meta.get("severity", "medium"))
        cwe = meta.get("cwe", "")
        owasp = meta.get("owasp", "")
        description = meta.get("description", f"YARA rule '{rule_name}' matched")

        match_strings = match.get("strings", [])
        matched_data = ""
        if match_strings and isinstance(match_strings, list):
            first = match_strings[0]
            if isinstance(first, dict):
                matched_data = first.get("data", "")[:200]
            elif isinstance(first, str):
                matched_data = first[:200]

        rule_id = f"BIN-yar-{rule_name}"
        fp = _fingerprint(target_name, rule_name, rule_id)

        findings.append(
            {
                "id": fp,
                "repo": target_name,
                "file": target_name,
                "line": None,
                "rule_id": rule_id,
                "severity": severity,
                "message": (
                    f"{description}. Matched: {matched_data}" if matched_data else description
                ),
                "cwe": cwe,
                "owasp": owasp,
                "scanner": "yara",
                "raw_severity": severity,
                "fingerprint": fp,
                "target_type": "binary",
                "target_name": target_name,
                "url": "",
                "http_method": "",
                "binary_hash": binary_hash,
                "hardening_check": "",
                "binary_section": "",
                "yara_rule": rule_name,
            }
        )

    return findings


# ── Parser: strings analysis ─────────────────────────────────────────────────


#: At most this many strings entries become findings (a strings dump can be enormous).
#: Entries beyond it are not parsed, and that is reported as a limitation that makes the
#: strings step partial: a cap on what is read is never silent.
MAX_STRINGS_FINDINGS = 50


def parse_strings_findings(
    data: dict,
    target_name: str,
    binary_hash: str = "",
    degraded: list[str] | None = None,
) -> list[dict]:
    findings_list = data.get("findings", [])
    if not isinstance(findings_list, list):
        raise ValueError("strings `findings` is not a list")
    results = []

    if len(findings_list) > MAX_STRINGS_FINDINGS and degraded is not None:
        degraded.append(
            f"only the first {MAX_STRINGS_FINDINGS} of {len(findings_list)} strings entries "
            f"were parsed; the other {len(findings_list) - MAX_STRINGS_FINDINGS} were not"
        )

    for i, item in enumerate(findings_list[:MAX_STRINGS_FINDINGS], 1):
        value = item.get("value", "") if isinstance(item, dict) else str(item)
        value = value.strip()
        if not value:
            continue

        if any(
            kw in value.lower()
            for kw in ("password", "passwd", "secret", "private_key", "api_key", "token")
        ):
            severity = "high"
            cwe = "CWE-798"
            owasp = "A07:2021"
            msg = f"Hardcoded credential pattern found in strings: {value[:100]}"
        elif value.startswith(("http://", "https://")):
            severity = "medium"
            cwe = "CWE-200"
            owasp = "A01:2021"
            msg = f"Embedded URL found in binary: {value[:100]}"
        elif any(c.isdigit() for c in value) and "." in value:
            severity = "low"
            cwe = "CWE-200"
            owasp = ""
            msg = f"Embedded IP/version string: {value[:100]}"
        else:
            severity = "info"
            cwe = ""
            owasp = ""
            msg = f"Suspicious string in binary: {value[:100]}"

        rule_id = f"BIN-str-{i}"
        fp = _fingerprint(target_name, value[:100], rule_id)

        results.append(
            {
                "id": fp,
                "repo": target_name,
                "file": target_name,
                "line": None,
                "rule_id": rule_id,
                "severity": severity,
                "message": msg,
                "cwe": cwe,
                "owasp": owasp,
                "scanner": "strings",
                "raw_severity": severity,
                "fingerprint": fp,
                "target_type": "binary",
                "target_name": target_name,
                "url": "",
                "http_method": "",
                "binary_hash": binary_hash,
                "hardening_check": "",
                "binary_section": "",
                "yara_rule": "",
            }
        )

    return results


# ── Auto-detect format ───────────────────────────────────────────────────────


def parse_strings_text(
    text: str,
    target_name: str,
    binary_hash: str = "",
    degraded: list[str] | None = None,
) -> list[dict]:
    """strings-findings.txt as examples.md A6 writes it: one grep match per line.

    An empty file is a real result (the grep matched nothing), not a missing one.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return parse_strings_findings(
        {"findings": [{"value": ln} for ln in lines]}, target_name, binary_hash, degraded
    )


# ── Parser: PE/ELF header analysis (A7) ──────────────────────────────────────

# header-analysis.json, written by examples.md A7:
#   {"format": "pe" | "elf", "checks": {"<check>": true | false, ...}}
# true = the property holds; false = it does not and becomes a finding.
HEADER_CHECK_META = {
    "signed": {
        "severity": "high",
        "cwe": "CWE-345",
        "owasp": "A08:2021",
        "message": "Binary is not signed — integrity and origin cannot be verified",
    },
    "debug_symbols_stripped": {
        "severity": "low",
        "cwe": "CWE-200",
        "owasp": "A05:2021",
        "message": "Debug symbols present in the shipped binary — internals are exposed",
    },
    "no_known_vulnerable_compiler": {
        "severity": "medium",
        "cwe": "CWE-1104",
        "owasp": "A06:2021",
        "message": "Built with a compiler or toolchain version with known defects",
    },
    "interpreter_trusted": {
        "severity": "medium",
        "cwe": "CWE-426",
        "owasp": "A08:2021",
        "message": "ELF interpreter is not a standard system loader",
    },
    "symbols_stripped": {
        "severity": "low",
        "cwe": "CWE-200",
        "owasp": "A05:2021",
        "message": "Symbol table present in the shipped binary — internals are exposed",
    },
    "no_writable_executable_sections": {
        "severity": "high",
        "cwe": "CWE-119",
        "owasp": "A06:2021",
        "message": "A section is both writable and executable",
    },
}


#: The check names examples.md A7 lists, per `format`. A header-analysis.json counts as
#: read only if it has at least one of these for its format, with a boolean value.
HEADER_FORMAT_CHECKS = {
    "pe": ("signed", "debug_symbols_stripped", "no_known_vulnerable_compiler"),
    "elf": ("interpreter_trusted", "symbols_stripped", "no_writable_executable_sections"),
}


def _clean_name(name: object, limit: int = 60) -> str:
    """A check name made safe to put in a rule id or message: printable, single-line, short.

    A name that needed cleaning or shortening gets a short hash of the original appended,
    so two different names never clean to the same text and merge into one finding.
    """
    raw = str(name)
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    if raw and cleaned == raw and len(raw) <= limit:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8", "backslashreplace")).hexdigest()[:8]
    return f"{cleaned[:40] or '?'}~{digest}"


def parse_header_json(
    data: dict,
    target_name: str,
    binary_hash: str = "",
    degraded: list[str] | None = None,
    notes: list[str] | None = None,
) -> list[dict]:
    """header-analysis.json -> findings; raises ValueError when it is not a usable result.

    Usable means: `format` is `pe` or `elf`, and `checks` has at least one check the doc
    lists for that format with a boolean value. A non-boolean value is never read as
    pass or fail: it is ignored and reported (`degraded`, so the step is partial). A
    name the doc does not list for the format keeps its documented medium finding when
    false, and is noted; it cannot make the file count as read by itself.
    """
    fmt = data.get("format")
    if not isinstance(fmt, str) or fmt not in HEADER_FORMAT_CHECKS:
        raise ValueError(f"unrecognised header format {_clean_name(fmt)!r}; expected pe or elf")
    checks = data["checks"]
    known = HEADER_FORMAT_CHECKS[fmt]
    if not any(isinstance(checks.get(k), bool) for k in known):
        raise ValueError(
            f"no recognised {fmt} check with a boolean value (expected one of {', '.join(known)})"
        )

    non_boolean = [_clean_name(k) for k, v in checks.items() if not isinstance(v, bool)]
    if non_boolean and degraded is not None:
        degraded.append(
            f"check(s) with a non-boolean value were ignored, not read as pass or fail: "
            f"{', '.join(non_boolean[:10])}" + (" ..." if len(non_boolean) > 10 else "")
        )
    unrecognised = [_clean_name(k) for k in checks if k not in known]
    if unrecognised and notes is not None:
        notes.append(
            f"unrecognised {fmt} check name(s), reported as medium findings when false: "
            f"{', '.join(unrecognised[:10])}" + (" ..." if len(unrecognised) > 10 else "")
        )

    findings = []
    for check_name, value in checks.items():
        if value is not False:
            continue
        safe = _clean_name(check_name)
        meta = HEADER_CHECK_META.get(check_name, {}) if check_name in known else {}
        rule_id = f"BIN-hdr-{safe}"
        fp = _fingerprint(target_name, f"header{safe}", rule_id)
        severity = meta.get("severity", "medium")
        findings.append(
            {
                "id": fp,
                "repo": target_name,
                "file": target_name,
                "line": None,
                "rule_id": rule_id,
                "severity": severity,
                "message": meta.get("message", f"Header check '{safe}' failed ({fmt})"),
                "cwe": meta.get("cwe", ""),
                "owasp": meta.get("owasp", ""),
                "scanner": "header_analysis",
                "raw_severity": severity,
                "fingerprint": fp,
                "target_type": "binary",
                "target_name": target_name,
                "url": "",
                "http_method": "",
                "binary_hash": binary_hash,
                "hardening_check": "",
                "binary_section": "",
                "yara_rule": "",
            }
        )
    return findings


def detect_step(data: object, filename: str = "") -> str | None:
    """Which planned step a parsed result file is the output of; None if it is none we read.

    Decided by content, not file name: a file called checksec.json holding an error
    object, or YARA output filed under the wrong name, must not count for the step.
    """
    if isinstance(data, dict):
        if isinstance(data.get("checks"), dict) and "format" in data:
            return "header_analysis"
        if "error" in data and len(data) == 1:
            return None
        for val in data.values():
            if isinstance(val, dict) and any(
                k in val for k in ("nx", "pie", "relro", "canary", "dep", "aslr", "cfg")
            ):
                return "checksec"
        if "file" in data and isinstance(data.get("file"), dict):
            return "checksec"
        if "matches" in data or "rules" in data:
            return "yara"
        if "findings" in data:
            return "strings"
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "rule" in data[0]:
            return "yara"
        if not data and "yara" in filename.lower():
            return "yara"  # `yara -j` with no match prints an empty list
    return None


def detect_and_parse(
    data: object,
    filename: str,
    target_name: str,
    binary_hash: str = "",
    degraded: list[str] | None = None,
    notes: list[str] | None = None,
) -> list[dict]:
    step = detect_step(data, filename)
    if step == "header_analysis":
        return parse_header_json(data, target_name, binary_hash, degraded, notes)
    if step == "checksec":
        return parse_checksec_json(data, target_name, binary_hash)
    if step == "yara":
        return parse_yara_json(data, target_name, binary_hash)
    if step == "strings":
        return parse_strings_findings(data, target_name, binary_hash, degraded)
    if isinstance(data, dict) and "error" in data and len(data) == 1:
        return []
    print(f"  [warn] Could not detect binary analysis format for {filename}", file=sys.stderr)
    return []


#: The result file each planned step leaves in the scan directory, by the exact name
#: examples.md tells the agent to write (A4-A7), mapped to the step it is the output of.
#: Only these names, only at the top level of the scan directory, are read: a stale
#: `old/checksec.json`, a `checksec-old.json` or a `strings-notes.txt` is not evidence
#: that a step ran. `strings-findings.json` is the name an earlier version of the doc
#: gave for strings; old scan directories may hold it.
RESULT_FILES = {
    "checksec.json": "checksec",
    "yara-matches.json": "yara",
    "strings-findings.txt": "strings",
    "strings-findings.json": "strings",
    "header-analysis.json": "header_analysis",
}


#: Name fragments that make a file in a scan directory look like a result of this mode, so one
#: that is not named exactly as documented is reported as ignored rather than silently skipped.
RESULT_HINTS = ("checksec", "yara", "strings", "header-analysis")


def read_result_file(path: Path, target_name: str, binary_hash: str) -> scan_coverage.Read:
    """Parse one result file into a scan_coverage.Read.

    The file counts for a step only if its content is that step's output: a checksec.json
    holding YARA output, or an error object, reads as no step. Raises on a file that
    cannot be read or parsed (the caller names it and the step stays unread).
    """
    expected = RESULT_FILES[path.name]
    degraded: list[str] = []
    notes: list[str] = []
    decoded = scan_coverage.decode_text(path.read_bytes(), path.name)
    notes.extend(decoded.notes)
    degraded.extend(decoded.degraded)
    if path.suffix == ".txt":
        step: str | None = expected
        findings = parse_strings_text(decoded.text, target_name, binary_hash, degraded)
    else:
        raw = json.loads(decoded.text)
        step = detect_step(raw, path.name)
        findings = detect_and_parse(raw, path.name, target_name, binary_hash, degraded, notes)
    if step != expected:
        notes.append(f"{path.name} is not a {expected} result (content reads as {step or 'none'})")
        return scan_coverage.Read(None, findings, [], notes)
    return scan_coverage.Read(step, findings, degraded, notes)


def is_result_file(path: Path) -> bool:
    """Result files this parser reads: the documented names, files only."""
    return path.name in RESULT_FILES and path.is_file()


# ── Deduplication ────────────────────────────────────────────────────────────


def deduplicate(findings: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for f in findings:
        fp = f["fingerprint"]
        if fp not in best:
            best[fp] = f
        else:
            existing_rank = SEVERITY_RANK.get(best[fp]["severity"], 0)
            new_rank = SEVERITY_RANK.get(f["severity"], 0)
            if new_rank > existing_rank:
                best[fp] = f
    return list(best.values())


# ── Sample data generator ────────────────────────────────────────────────────


def generate_sample() -> list[dict]:
    binary_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    raw = [
        {
            "target_name": "data-processor",
            "rule_id": "BIN-chk-nx",
            "severity": "high",
            "message": "NX (Non-Executable Stack) not enabled — stack buffer overflows can execute code",
            "cwe": "CWE-119",
            "owasp": "A06:2021",
            "scanner": "checksec",
            "hardening_check": "nx",
            "yara_rule": "",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-chk-pie",
            "severity": "high",
            "message": "PIE (Position Independent Executable) not enabled — ASLR ineffective",
            "cwe": "CWE-119",
            "owasp": "A06:2021",
            "scanner": "checksec",
            "hardening_check": "pie",
            "yara_rule": "",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-chk-canary",
            "severity": "high",
            "message": "Stack canaries not enabled — stack buffer overflow protection missing",
            "cwe": "CWE-121",
            "owasp": "A06:2021",
            "scanner": "checksec",
            "hardening_check": "canary",
            "yara_rule": "",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-yar-hardcoded-password",
            "severity": "high",
            "message": "YARA rule 'HardcodedPassword' matched. Matched: password=admin123",
            "cwe": "CWE-798",
            "owasp": "A07:2021",
            "scanner": "yara",
            "hardening_check": "",
            "yara_rule": "HardcodedPassword",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-yar-internal-url",
            "severity": "medium",
            "message": "YARA rule 'EmbeddedInternalURL' matched. Matched: http://192.168.1.50:5432",
            "cwe": "CWE-200",
            "owasp": "",
            "scanner": "yara",
            "hardening_check": "",
            "yara_rule": "EmbeddedInternalURL",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-str-1",
            "severity": "high",
            "message": "Hardcoded credential pattern found in strings: DB_PASSWORD=kr0g3r_pr0d_2026",
            "cwe": "CWE-798",
            "owasp": "A07:2021",
            "scanner": "strings",
            "hardening_check": "",
            "yara_rule": "",
        },
        {
            "target_name": "data-processor",
            "rule_id": "BIN-str-2",
            "severity": "medium",
            "message": "Embedded URL found in binary: https://internal-api.acme-corp.com/v2/data",
            "cwe": "CWE-200",
            "owasp": "A01:2021",
            "scanner": "strings",
            "hardening_check": "",
            "yara_rule": "",
        },
    ]

    findings = []
    for r in raw:
        fp = _fingerprint(
            r["target_name"],
            r.get("hardening_check", "") or r.get("yara_rule", "") or r["rule_id"],
            r["rule_id"],
        )
        findings.append(
            {
                "id": fp,
                "repo": r["target_name"],
                "file": r["target_name"],
                "line": None,
                "rule_id": r["rule_id"],
                "severity": r["severity"],
                "message": r["message"],
                "cwe": r["cwe"],
                "owasp": r["owasp"],
                "scanner": r["scanner"],
                "raw_severity": r["severity"],
                "fingerprint": fp,
                "target_type": "binary",
                "target_name": r["target_name"],
                "url": "",
                "http_method": "",
                "binary_hash": binary_hash,
                "hardening_check": r.get("hardening_check", ""),
                "binary_section": "",
                "yara_rule": r.get("yara_rule", ""),
            }
        )
    return findings


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize binary analysis outputs (checksec, YARA, strings)"
    )
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--scans-dir", help="Directory containing binary analysis results")
    parser.add_argument("--output", help="Output file path. Default: stdout")
    parser.add_argument(
        "--coverage-output",
        help="Write per-scan coverage (complete|partial|unknown, skipped steps, limitations) "
        "to this JSON file. Needed to see coverage on a scan that produced no findings.",
    )
    parser.add_argument("--sample", action="store_true", help="Generate synthetic sample findings")
    args = parser.parse_args()

    scan_reports: list[dict] = []

    if args.sample:
        findings = generate_sample()
        sample = scan_coverage.unknown_report(None, "synthetic sample data; no scan was run")
        scan_coverage.stamp(findings, sample)
        scan_reports.append(sample)
        print(f"[parse_binary] Generated {len(findings)} sample binary findings", file=sys.stderr)
        scan_coverage.report("parse_binary", scan_reports, args.coverage_output)
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
            print(f"[parse_binary] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            scan_coverage.report("parse_binary", scan_reports, args.coverage_output)
            sys.exit(1)

        hash_file = scans_dir / "hash.json"
        binary_hash = ""
        if hash_file.exists():
            try:
                hash_data = json.loads(hash_file.read_text(encoding="utf-8"))
                binary_hash = hash_data.get("binary_hash", "")
            except Exception:
                pass

        try:
            candidates = sorted(f for f in scans_dir.rglob("*") if is_result_file(f))
            all_findings, reports, n_files = scan_coverage.collect(
                "parse_binary",
                scans_dir,
                candidates,
                PLANNED_STEPS,
                lambda path, target: read_result_file(path, target, binary_hash),
                RESULT_FILES,
                RESULT_HINTS,
            )
        except Exception as exc:  # noqa: BLE001 - never exit without the coverage sidecar
            print(f"[parse_binary] ERROR: reading results failed: {exc}", file=sys.stderr)
            scan_reports.append(
                scan_coverage.unknown_report(
                    str(scans_dir),
                    f"unexpected failure while reading results: {scan_coverage.short(exc)}",
                )
            )
            scan_coverage.report("parse_binary", scan_reports, args.coverage_output)
            sys.exit(1)
        scan_reports.extend(reports)

        if not n_files:
            print(
                f"[parse_binary] No checksec/yara/strings files found in {scans_dir}",
                file=sys.stderr,
            )
            scan_coverage.report("parse_binary", scan_reports, args.coverage_output)
            sys.exit(1)

        findings = deduplicate(all_findings)
        print(
            f"[parse_binary] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )
        scan_coverage.report("parse_binary", scan_reports, args.coverage_output)

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_binary] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
