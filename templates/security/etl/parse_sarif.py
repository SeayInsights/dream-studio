"""
parse_sarif.py — SARIF/scanner output parser and normalizer.

Reads scan results from ~/.dream-studio/security/scans/{client}/
Supports: Semgrep SARIF, Bandit JSON, TruffleHog JSON, pip-audit JSON
Outputs: normalized flat findings list as JSON (stdout or file)

Usage:
    py -3.12 parse_sarif.py --client <name> [--scans-dir <path>] [--output <path>]
    py -3.12 parse_sarif.py --sample --client <name>
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# ── Severity ranking for deduplication (higher index = higher severity) ───────
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# ── OWASP / CWE maps for common Bandit test IDs ──────────────────────────────
BANDIT_CWE_MAP = {
    "B101": "CWE-617",  "B102": "CWE-78",  "B103": "CWE-732",
    "B104": "CWE-605",  "B105": "CWE-259", "B106": "CWE-259",
    "B107": "CWE-259",  "B108": "CWE-377", "B110": "CWE-390",
    "B112": "CWE-390",  "B201": "CWE-78",  "B301": "CWE-502",
    "B302": "CWE-502",  "B303": "CWE-327", "B304": "CWE-327",
    "B305": "CWE-327",  "B306": "CWE-377", "B307": "CWE-78",
    "B308": "CWE-79",   "B310": "CWE-601", "B311": "CWE-330",
    "B312": "CWE-319",  "B313": "CWE-611", "B314": "CWE-611",
    "B315": "CWE-611",  "B316": "CWE-611", "B317": "CWE-611",
    "B318": "CWE-611",  "B319": "CWE-611", "B320": "CWE-611",
    "B321": "CWE-321",  "B322": "CWE-89",  "B323": "CWE-295",
    "B324": "CWE-327",  "B325": "CWE-330", "B401": "CWE-676",
    "B402": "CWE-676",  "B403": "CWE-676", "B404": "CWE-78",
    "B405": "CWE-676",  "B406": "CWE-676", "B407": "CWE-676",
    "B408": "CWE-676",  "B409": "CWE-676", "B410": "CWE-676",
    "B411": "CWE-676",  "B412": "CWE-676", "B413": "CWE-676",
    "B501": "CWE-295",  "B502": "CWE-295", "B503": "CWE-295",
    "B504": "CWE-295",  "B505": "CWE-326", "B506": "CWE-20",
    "B507": "CWE-295",  "B601": "CWE-78",  "B602": "CWE-78",
    "B603": "CWE-78",   "B604": "CWE-78",  "B605": "CWE-78",
    "B606": "CWE-78",   "B607": "CWE-78",  "B608": "CWE-89",
    "B609": "CWE-78",   "B610": "CWE-89",  "B611": "CWE-89",
    "B701": "CWE-79",   "B702": "CWE-79",  "B703": "CWE-79",
}

BANDIT_OWASP_MAP = {
    "B105": "A07:2021", "B106": "A07:2021", "B107": "A07:2021",
    "B301": "A08:2021", "B302": "A08:2021",
    "B303": "A02:2021", "B304": "A02:2021", "B305": "A02:2021",
    "B307": "A03:2021", "B322": "A03:2021", "B608": "A03:2021",
    "B610": "A03:2021", "B611": "A03:2021",
    "B308": "A03:2021", "B701": "A03:2021", "B702": "A03:2021",
    "B501": "A02:2021", "B502": "A02:2021", "B503": "A02:2021",
    "B504": "A02:2021", "B505": "A02:2021", "B507": "A02:2021",
    "B601": "A03:2021", "B602": "A03:2021", "B603": "A03:2021",
    "B604": "A03:2021", "B605": "A03:2021",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fingerprint(repo: str, file: str, line: int | None, rule_id: str) -> str:
    raw = f"{repo}|{file}|{line}|{rule_id}"
    return "sha256-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _normalize_severity(raw: str) -> str:
    mapping = {
        "error": "high", "warning": "medium", "note": "low",
        "none": "info",
        "high": "high", "medium": "medium", "low": "low",
        "critical": "critical", "info": "info",
        # Bandit SEVERITY variants
        "HIGH": "high", "MEDIUM": "medium", "LOW": "low",
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
    for run in data.get("runs", []):
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

            findings.append({
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
            })
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
        findings.append({
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
        })
    return findings


# ── Parser: TruffleHog JSON ───────────────────────────────────────────────────

def parse_trufflehog(data_list: list, repo: str) -> list[dict]:
    findings = []
    if isinstance(data_list, dict):
        data_list = data_list.get("results", [data_list])
    for r in data_list:
        detector = r.get("DetectorName", "secret")
        raw = r.get("Raw", "")[:80]  # truncate sensitive raw value
        meta = r.get("SourceMetadata", {}).get("Data", {})
        # TruffleHog metadata varies by source type; try common keys
        filename = (
            meta.get("Filesystem", {}).get("file")
            or meta.get("Git", {}).get("file")
            or meta.get("file", "")
        )
        line = (
            meta.get("Filesystem", {}).get("line")
            or meta.get("Git", {}).get("line")
        )
        rule_id = f"TH-{detector}"
        fp = _fingerprint(repo, filename or "", line, rule_id)
        findings.append({
            "id": fp,
            "repo": repo,
            "file": filename or "",
            "line": line,
            "rule_id": rule_id,
            "severity": "critical",
            "message": f"Secret detected by {detector}: {raw!r}",
            "cwe": "CWE-312",
            "owasp": "A02:2021",
            "scanner": "trufflehog",
            "raw_severity": "CRITICAL",
            "fingerprint": fp,
            "target_type": "repo",
            "target_name": "",
            "url": "",
            "http_method": "",
            "binary_hash": "",
        })
    return findings


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
            findings.append({
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
            })
    return findings


# ── Auto-detect scanner from file content ─────────────────────────────────────

def detect_and_parse(data: object, filename: str, repo: str) -> list[dict]:
    # SARIF: has $schema or runs[].results[]
    if isinstance(data, dict):
        schema = data.get("$schema", "")
        if "sarif" in schema.lower() or ("runs" in data and "results" in data.get("runs", [{}])[0]):
            return parse_semgrep_sarif(data, repo)

        # Bandit: has 'results' list with 'test_id' or 'issue_severity'
        if "results" in data and isinstance(data["results"], list):
            sample = data["results"][0] if data["results"] else {}
            if "test_id" in sample or "issue_severity" in sample:
                return parse_bandit(data, repo)
            # TruffleHog dict wrapper
            if "DetectorName" in sample or "SourceMetadata" in sample:
                return parse_trufflehog(data["results"], repo)

        # pip-audit dict wrapper
        if "dependencies" in data:
            return parse_pip_audit(data["dependencies"], repo)

    # pip-audit: top-level list of {name, version, vulns}
    if isinstance(data, list):
        sample = data[0] if data else {}
        if "vulns" in sample:
            return parse_pip_audit(data, repo)
        # TruffleHog top-level list
        if "DetectorName" in sample or "SourceMetadata" in sample:
            return parse_trufflehog(data, repo)

    print(f"  [warn] Could not detect scanner format for {filename}", file=sys.stderr)
    return []


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate(findings: list[dict]) -> list[dict]:
    """Keep one finding per fingerprint; prefer highest severity."""
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
        findings.append({
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
        })
    return findings


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize security scanner outputs (SARIF, Bandit, TruffleHog, pip-audit)"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. plmarketing-kroger)")
    parser.add_argument(
        "--scans-dir",
        help="Directory containing scan files. Default: ~/.dream-studio/security/scans/{client}/",
    )
    parser.add_argument("--output", help="Output file path. Default: stdout")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Generate synthetic sample findings for pipeline testing",
    )
    args = parser.parse_args()

    if args.sample:
        findings = generate_sample()
        print(f"[parse_sarif] Generated {len(findings)} sample findings", file=sys.stderr)
    else:
        scans_dir = Path(
            args.scans_dir
            or os.path.expanduser(f"~/.dream-studio/security/scans/{args.client}/")
        )
        if not scans_dir.exists():
            print(f"[parse_sarif] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            sys.exit(1)

        scan_files = sorted(
            f for f in scans_dir.iterdir()
            if f.suffix in (".json", ".sarif") and f.is_file()
        )
        if not scan_files:
            print(f"[parse_sarif] No .json/.sarif files found in {scans_dir}", file=sys.stderr)
            sys.exit(1)

        all_findings: list[dict] = []
        for sf in scan_files:
            repo = _repo_from_path(sf.stem)
            print(f"[parse_sarif] Parsing {sf.name} → repo={repo}", file=sys.stderr)
            try:
                with open(sf, encoding="utf-8") as fh:
                    raw = json.load(fh)
                parsed = detect_and_parse(raw, sf.name, repo)
                print(f"  → {len(parsed)} findings", file=sys.stderr)
                all_findings.extend(parsed)
            except Exception as exc:
                print(f"  [error] Failed to parse {sf.name}: {exc}", file=sys.stderr)

        findings = deduplicate(all_findings)
        print(
            f"[parse_sarif] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_sarif] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
