"""
parse_binary.py — Binary analysis result parser and normalizer.

Reads binary analysis results from ~/.dream-studio/security/scans/{client}/
Supports: checksec JSON, YARA JSON, strings analysis output
Outputs: normalized flat findings list as JSON (stdout or file)

Usage:
    py -3.12 parse_binary.py --client <name> [--scans-dir <path>] [--output <path>]
    py -3.12 parse_binary.py --sample --client <name>
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

CHECKSEC_CHECK_META = {
    "nx": {"severity": "high", "cwe": "CWE-119", "owasp": "A06:2021",
           "message": "NX (Non-Executable Stack) not enabled — stack buffer overflows can execute code"},
    "pie": {"severity": "high", "cwe": "CWE-119", "owasp": "A06:2021",
            "message": "PIE (Position Independent Executable) not enabled — ASLR ineffective"},
    "relro": {"severity": "medium", "cwe": "CWE-119", "owasp": "A06:2021",
              "message": "Full RELRO not enabled — GOT overwrite attacks possible"},
    "canary": {"severity": "high", "cwe": "CWE-121", "owasp": "A06:2021",
               "message": "Stack canaries not enabled — stack buffer overflow protection missing"},
    "fortify": {"severity": "medium", "cwe": "CWE-120", "owasp": "A06:2021",
                "message": "FORTIFY_SOURCE not enabled — no bounds checking on libc functions"},
    "runpath": {"severity": "medium", "cwe": "CWE-426", "owasp": "A06:2021",
                "message": "RUNPATH/RPATH set to writable directory — DLL/shared library hijacking possible"},
    "dep": {"severity": "high", "cwe": "CWE-119", "owasp": "A06:2021",
            "message": "DEP (Data Execution Prevention) not enabled"},
    "aslr": {"severity": "high", "cwe": "CWE-119", "owasp": "A06:2021",
             "message": "ASLR not enabled — memory layout predictable"},
    "cfg": {"severity": "medium", "cwe": "CWE-119", "owasp": "A06:2021",
            "message": "Control Flow Guard (CFG) not enabled"},
    "safeseh": {"severity": "medium", "cwe": "CWE-119", "owasp": "A06:2021",
                "message": "SafeSEH not enabled — SEH overwrite attacks possible"},
    "authenticode": {"severity": "high", "cwe": "CWE-345", "owasp": "A08:2021",
                     "message": "Binary not signed with Authenticode — integrity cannot be verified"},
    "high_entropy_va": {"severity": "low", "cwe": "CWE-119", "owasp": "A06:2021",
                        "message": "High Entropy VA not enabled — 64-bit ASLR less effective"},
    "code_sign": {"severity": "high", "cwe": "CWE-345", "owasp": "A08:2021",
                  "message": "Code signature missing or invalid"},
    "hardened_runtime": {"severity": "medium", "cwe": "CWE-693", "owasp": "A05:2021",
                         "message": "Hardened runtime not enabled"},
    "arc": {"severity": "low", "cwe": "CWE-416", "owasp": "A06:2021",
            "message": "ARC (Automatic Reference Counting) not enabled — use-after-free risk"},
}


def _fingerprint(target: str, check: str, rule_id: str) -> str:
    raw = f"{target}|{check}|{rule_id}"
    return "sha256-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_severity(raw: str) -> str:
    mapping = {
        "high": "high", "medium": "medium", "low": "low",
        "critical": "critical", "info": "info",
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

            meta = CHECKSEC_CHECK_META.get(check_name_lower, CHECKSEC_CHECK_META.get(check_name.lower(), {}))
            severity = meta.get("severity", "medium")
            cwe = meta.get("cwe", "CWE-119")
            owasp = meta.get("owasp", "A06:2021")
            message = meta.get("message", f"Hardening check '{check_name}' failed (value: {check_value})")

            rule_id = f"BIN-chk-{check_name.lower()}"
            fp = _fingerprint(target_name, binary_name + check_name, rule_id)

            findings.append({
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
            })

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

        findings.append({
            "id": fp,
            "repo": target_name,
            "file": target_name,
            "line": None,
            "rule_id": rule_id,
            "severity": severity,
            "message": f"{description}. Matched: {matched_data}" if matched_data else description,
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
        })

    return findings


# ── Parser: strings analysis ─────────────────────────────────────────────────

def parse_strings_findings(data: dict, target_name: str, binary_hash: str = "") -> list[dict]:
    findings_list = data.get("findings", [])
    results = []

    for i, item in enumerate(findings_list[:50], 1):
        value = item.get("value", "") if isinstance(item, dict) else str(item)
        value = value.strip()
        if not value:
            continue

        if any(kw in value.lower() for kw in ("password", "passwd", "secret", "private_key", "api_key", "token")):
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

        results.append({
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
        })

    return results


# ── Auto-detect format ───────────────────────────────────────────────────────

def detect_and_parse(data: object, filename: str, target_name: str, binary_hash: str = "") -> list[dict]:
    if isinstance(data, dict):
        if "error" in data and len(data) == 1:
            return []

        for val in data.values():
            if isinstance(val, dict) and any(
                k in val for k in ("nx", "pie", "relro", "canary", "dep", "aslr", "cfg")
            ):
                return parse_checksec_json(data, target_name, binary_hash)

        if "file" in data and isinstance(data.get("file"), dict):
            return parse_checksec_json(data, target_name, binary_hash)

        if "matches" in data or "rules" in data:
            return parse_yara_json(data, target_name, binary_hash)

        if "findings" in data:
            return parse_strings_findings(data, target_name, binary_hash)

    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "rule" in data[0]:
            return parse_yara_json(data, target_name, binary_hash)

    print(f"  [warn] Could not detect binary analysis format for {filename}", file=sys.stderr)
    return []


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
            "message": "Embedded URL found in binary: https://internal-api.plmarketing.com/v2/data",
            "cwe": "CWE-200",
            "owasp": "A01:2021",
            "scanner": "strings",
            "hardening_check": "",
            "yara_rule": "",
        },
    ]

    findings = []
    for r in raw:
        fp = _fingerprint(r["target_name"], r.get("hardening_check", "") or r.get("yara_rule", "") or r["rule_id"], r["rule_id"])
        findings.append({
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
        })
    return findings


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize binary analysis outputs (checksec, YARA, strings)"
    )
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--scans-dir", help="Directory containing binary analysis results")
    parser.add_argument("--output", help="Output file path. Default: stdout")
    parser.add_argument("--sample", action="store_true", help="Generate synthetic sample findings")
    args = parser.parse_args()

    if args.sample:
        findings = generate_sample()
        print(f"[parse_binary] Generated {len(findings)} sample binary findings", file=sys.stderr)
    else:
        scans_dir = Path(
            args.scans_dir
            or os.path.expanduser(f"~/.dream-studio/security/scans/{args.client}/")
        )
        if not scans_dir.exists():
            print(f"[parse_binary] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            sys.exit(1)

        hash_file = scans_dir / "hash.json"
        binary_hash = ""
        if hash_file.exists():
            try:
                hash_data = json.loads(hash_file.read_text(encoding="utf-8"))
                binary_hash = hash_data.get("binary_hash", "")
            except Exception:
                pass

        scan_files = sorted(
            f for f in scans_dir.rglob("*")
            if f.suffix == ".json" and f.is_file()
            and any(k in f.name.lower() for k in ("checksec", "yara", "strings"))
        )
        if not scan_files:
            print(f"[parse_binary] No checksec/yara/strings files found in {scans_dir}", file=sys.stderr)
            sys.exit(1)

        all_findings: list[dict] = []
        for sf in scan_files:
            target_name = sf.parent.parent.name if sf.parent.name.count("-") == 2 else sf.parent.name
            print(f"[parse_binary] Parsing {sf.name} → target={target_name}", file=sys.stderr)
            try:
                with open(sf, encoding="utf-8") as fh:
                    raw = json.load(fh)
                parsed = detect_and_parse(raw, sf.name, target_name, binary_hash)
                print(f"  → {len(parsed)} findings", file=sys.stderr)
                all_findings.extend(parsed)
            except Exception as exc:
                print(f"  [error] Failed to parse {sf.name}: {exc}", file=sys.stderr)

        findings = deduplicate(all_findings)
        print(
            f"[parse_binary] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_binary] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
