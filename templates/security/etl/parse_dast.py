"""
parse_dast.py — DAST result parser and normalizer.

Reads DAST scan results from ~/.dream-studio/security/scans/{client}/
Supports: OWASP ZAP JSON reports, Nuclei JSONL output
Outputs: normalized flat findings list as JSON (stdout or file)

Every finding carries `coverage` (complete | partial | unknown) and `limitations`,
(see scan_coverage.py). `complete` needs the run record in the scan's scan-meta.json
to say both scanners ran AND this parser to have read a result for each
(zap-report.json, nuclei-output.jsonl): a run that continued with ZAP only because
Nuclei is not installed, or whose output is missing or malformed, is partial and names
the scanner; a scan directory with no usable run record is unknown, never complete.
A scan with zero findings carries nothing on a finding, so `--coverage-output`
writes the same facts per scan directory, and writes them before any non-zero exit.

Usage:
    py -3.12 parse_dast.py --client <name> [--scans-dir <path>] [--output <path>]
                           [--coverage-output <path>]
    py -3.12 parse_dast.py --sample --client <name>
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

#: Every scanner `dast run` executes when all its tooling is present (examples.md R3-R4).
#: Coverage is complete only when each one is recorded as run.
PLANNED_STEPS = ("zap", "nuclei")

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

ZAP_RISK_MAP = {0: "info", 1: "low", 2: "medium", 3: "high"}

ZAP_CWE_MAP = {
    "10010": "CWE-16",  # Cookie No HttpOnly Flag
    "10011": "CWE-614",  # Cookie Without Secure Flag
    "10012": "CWE-525",  # Password Autocomplete in Browser
    "10015": "CWE-693",  # Re-examine Cache-control Directives
    "10016": "CWE-311",  # Web Browser XSS Protection Not Enabled
    "10017": "CWE-200",  # Cross-Domain JavaScript Source File Inclusion
    "10019": "CWE-16",  # Content-Type Header Missing
    "10020": "CWE-693",  # X-Frame-Options Header
    "10021": "CWE-693",  # X-Content-Type-Options Header Missing
    "10023": "CWE-693",  # Information Disclosure - Debug Error Messages
    "10024": "CWE-539",  # Information Disclosure - Sensitive Info in URL
    "10025": "CWE-200",  # Information Disclosure - Sensitive Info in HTTP Referrer
    "10027": "CWE-200",  # Information Disclosure - Suspicious Comments
    "10028": "CWE-200",  # Open Redirect
    "10029": "CWE-16",  # Cookie Poisoning
    "10030": "CWE-693",  # User Controllable Charset
    "10031": "CWE-693",  # User Controllable HTML Element Attribute
    "10032": "CWE-16",  # Viewstate
    "10033": "CWE-16",  # Directory Browsing
    "10034": "CWE-548",  # Heartbleed OpenSSL Vulnerability
    "10035": "CWE-693",  # Strict-Transport-Security Header
    "10036": "CWE-200",  # Server Leaks Version Information
    "10037": "CWE-200",  # Server Leaks Information via X-Powered-By
    "10038": "CWE-16",  # Content Security Policy (CSP) Header Not Set
    "10039": "CWE-693",  # X-Backend-Server Header Information Leak
    "10040": "CWE-523",  # Secure Pages Include Mixed Content
    "10049": "CWE-16",  # Storable and Cacheable Content
    "10050": "CWE-693",  # Retrieved from Cache
    "10054": "CWE-1275",  # Cookie without SameSite Attribute
    "10055": "CWE-693",  # CSP
    "10096": "CWE-200",  # Timestamp Disclosure
    "10097": "CWE-16",  # Insufficient Site Isolation Against Spectre
    "10098": "CWE-16",  # Cross-Domain Misconfiguration
    "10105": "CWE-16",  # Weak Authentication Method
    "10202": "CWE-200",  # Absence of Anti-CSRF Tokens
    "20012": "CWE-20",  # Anti-CSRF Tokens Check
    "20014": "CWE-20",  # HTTP Parameter Pollution
    "20019": "CWE-16",  # External Redirect
    "30001": "CWE-311",  # Buffer Overflow
    "30002": "CWE-89",  # Format String Error
    "30003": "CWE-22",  # Integer Overflow Error
    "40003": "CWE-352",  # CRLF Injection
    "40008": "CWE-22",  # Path Traversal
    "40009": "CWE-918",  # Server Side Request Forgery
    "40012": "CWE-79",  # Cross Site Scripting (Reflected)
    "40013": "CWE-384",  # Session Fixation
    "40014": "CWE-79",  # Cross Site Scripting (Persistent)
    "40016": "CWE-94",  # Cross Site Scripting (Persistent) - Prime
    "40017": "CWE-79",  # Cross Site Scripting (Persistent) - Spider
    "40018": "CWE-89",  # SQL Injection
    "40019": "CWE-89",  # SQL Injection - MySQL
    "40020": "CWE-89",  # SQL Injection - Hypersonic SQL
    "40021": "CWE-89",  # SQL Injection - Oracle
    "40022": "CWE-89",  # SQL Injection - PostgreSQL
    "40024": "CWE-89",  # SQL Injection - SQLite
    "40026": "CWE-78",  # Cross Site Scripting (DOM Based)
    "40027": "CWE-89",  # SQL Injection - MsSQL
    "40028": "CWE-611",  # ELMAH Information Leak
    "40029": "CWE-209",  # Trace.axd Information Leak
    "40032": "CWE-200",  # .htaccess Information Leak
    "40034": "CWE-200",  # .env Information Leak
    "40035": "CWE-200",  # Hidden File Finder
    "40038": "CWE-200",  # Bypassing 403
    "40039": "CWE-200",  # Web Cache Deception
    "40040": "CWE-942",  # CORS Misconfiguration
    "40042": "CWE-829",  # Spring Actuator Information Leak
    "40043": "CWE-94",  # Log4Shell
    "40044": "CWE-400",  # Exponential Entity Expansion (Billion Laughs)
    "40045": "CWE-94",  # Spring4Shell
    "90001": "CWE-541",  # Insecure JSF ViewState
    "90011": "CWE-16",  # Charset Mismatch
    "90019": "CWE-16",  # Server Side Code Injection
    "90020": "CWE-601",  # Remote OS Command Injection
    "90021": "CWE-79",  # XPath Injection
    "90022": "CWE-209",  # Application Error Disclosure
    "90023": "CWE-611",  # XML External Entity Attack
    "90024": "CWE-94",  # Generic Padding Oracle
    "90025": "CWE-94",  # Expression Language Injection
    "90026": "CWE-78",  # SOAP Action Spoofing
    "90028": "CWE-200",  # Insecure HTTP Method
    "90029": "CWE-200",  # SOAP XML Injection
    "90030": "CWE-200",  # WSDL File Detection
    "90033": "CWE-200",  # Loosely Scoped Cookie
    "90034": "CWE-693",  # Cloud Metadata Potentially Exposed
}

ZAP_OWASP_MAP = {
    "40012": "A03:2021",
    "40014": "A03:2021",
    "40016": "A03:2021",
    "40017": "A03:2021",
    "40026": "A03:2021",
    "90021": "A03:2021",
    "40018": "A03:2021",
    "40019": "A03:2021",
    "40020": "A03:2021",
    "40021": "A03:2021",
    "40022": "A03:2021",
    "40024": "A03:2021",
    "40027": "A03:2021",
    "90019": "A03:2021",
    "90020": "A03:2021",
    "40003": "A03:2021",
    "40008": "A01:2021",
    "40009": "A10:2021",
    "10011": "A02:2021",
    "10054": "A02:2021",
    "10040": "A02:2021",
    "10038": "A05:2021",
    "10055": "A05:2021",
    "10020": "A05:2021",
    "10035": "A05:2021",
    "10021": "A05:2021",
    "10016": "A05:2021",
    "10202": "A01:2021",
    "40013": "A07:2021",
    "40040": "A05:2021",
    "40043": "A06:2021",
    "40045": "A06:2021",
    "90023": "A05:2021",
    "90034": "A05:2021",
}

NUCLEI_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "info",
    "unknown": "low",
}


def _fingerprint(target: str, url: str, rule_id: str) -> str:
    raw = f"{target}|{url}|{rule_id}"
    return "sha256-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Parser: OWASP ZAP JSON ──────────────────────────────────────────────────


def parse_zap_json(data: dict, target_name: str) -> list[dict]:
    findings = []
    site_list = data.get("site", [])
    if isinstance(site_list, dict):
        site_list = [site_list]

    for site in site_list:
        base_url = site.get("@name", "")
        for alert in site.get("alerts", []):
            plugin_id = str(alert.get("pluginid", ""))
            risk = alert.get("riskcode", 0)
            severity = ZAP_RISK_MAP.get(int(risk) if str(risk).isdigit() else 0, "info")
            rule_id = f"DAST-zap-{plugin_id}"
            name = alert.get("name", "")
            desc = alert.get("desc", "")
            cwe_id = alert.get("cweid", "")
            cwe = (
                f"CWE-{cwe_id}"
                if cwe_id and str(cwe_id) != "-1"
                else ZAP_CWE_MAP.get(plugin_id, "")
            )
            owasp = ZAP_OWASP_MAP.get(plugin_id, "")

            instances = alert.get("instances", [])
            if isinstance(instances, dict):
                instances = [instances]

            if not instances:
                instances = [{}]

            for inst in instances:
                url = inst.get("uri", base_url)
                method = inst.get("method", "")
                param = inst.get("param", "")
                evidence = inst.get("evidence", "")
                attack = inst.get("attack", "")

                fp = _fingerprint(target_name, url + param, rule_id)
                findings.append(
                    {
                        "id": fp,
                        "repo": target_name,
                        "file": url,
                        "line": None,
                        "rule_id": rule_id,
                        "severity": severity,
                        "message": f"{name}: {desc[:200]}" if desc else name,
                        "cwe": cwe,
                        "owasp": owasp,
                        "scanner": "zap",
                        "raw_severity": str(risk),
                        "fingerprint": fp,
                        "target_type": "webapp",
                        "target_name": target_name,
                        "url": url,
                        "http_method": method,
                        "binary_hash": "",
                        "parameter": param,
                        "response_code": "",
                        "evidence": evidence[:500] if evidence else "",
                        "attack_vector": attack[:500] if attack else "",
                    }
                )
    return findings


# ── Parser: Nuclei JSONL ─────────────────────────────────────────────────────


def _nuclei_shape_problem(obj: object) -> str | None:
    """Why a parsed JSONL line is not a Nuclei result; None when it is.

    A Nuclei result has the keys parse_nuclei_jsonl reads: an `info` object and a
    template id (`template-id`, or `templateID` in older versions). ZAP JSON or any
    other object is not one, and must not count as Nuclei's output.
    """
    if not isinstance(obj, dict):
        return "not a JSON object"
    if not isinstance(obj.get("info"), dict):
        return "no `info` object"
    if not isinstance(obj.get("template-id", obj.get("templateID")), str):
        return "no template id"
    return None


def nuclei_problems(text: str) -> list[str]:
    """Every non-empty line of a Nuclei -jsonl file that is not a Nuclei result.

    An empty file has none: Nuclei ran and found nothing, which is a real result.
    """
    problems = []
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, RecursionError):
            problems.append(f"line {line_num} is not valid JSON")
            continue
        reason = _nuclei_shape_problem(obj)
        if reason:
            problems.append(f"line {line_num} is {reason}")
    return problems


def parse_nuclei_jsonl(path: Path, target_name: str, text: str | None = None) -> list[dict]:
    """Findings from the lines that are Nuclei results; other lines are skipped with a warning.

    `text` is the decoded file (see scan_coverage.decode_text); read from `path` when omitted.
    """
    findings = []
    if text is None:
        text = path.read_text(encoding="utf-8")
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            print(
                f"  [warn] Skipping malformed line {line_num} in {path.name}", file=sys.stderr
            )
            continue
        if _nuclei_shape_problem(obj):
            print(
                f"  [warn] Skipping line {line_num} in {path.name}: not a nuclei result",
                file=sys.stderr,
            )
            continue

        template_id = obj.get("template-id", obj.get("templateID", "unknown"))
        info = obj.get("info", {})
        raw_sev = info.get("severity", "low")
        severity = NUCLEI_SEVERITY_MAP.get(raw_sev, "low")
        name = info.get("name", template_id)
        desc = info.get("description", "")
        classification = info.get("classification", {})
        cwe_list = classification.get("cwe-id", [])
        cwe = cwe_list[0] if cwe_list else ""
        if cwe and not cwe.startswith("CWE-"):
            cwe = f"CWE-{cwe}"

        matched_at = obj.get("matched-at", obj.get("matched_at", ""))
        url = obj.get("host", matched_at)
        method = obj.get("request", "").split(" ")[0] if obj.get("request") else ""
        curl_cmd = obj.get("curl-command", "")

        rule_id = f"DAST-nuc-{template_id}"
        fp = _fingerprint(target_name, url, rule_id)

        tags = info.get("tags", [])
        owasp = ""
        for tag in (tags if isinstance(tags, list) else tags.split(",")):
            tag = tag.strip()
            if tag.startswith("owasp-"):
                owasp = tag.replace("owasp-", "").upper()
                break

        findings.append(
            {
                "id": fp,
                "repo": target_name,
                "file": url,
                "line": None,
                "rule_id": rule_id,
                "severity": severity,
                "message": f"{name}: {desc[:200]}" if desc else name,
                "cwe": cwe,
                "owasp": owasp,
                "scanner": "nuclei",
                "raw_severity": raw_sev,
                "fingerprint": fp,
                "target_type": "webapp",
                "target_name": target_name,
                "url": url,
                "http_method": method,
                "binary_hash": "",
                "parameter": "",
                "response_code": "",
                "evidence": obj.get("response", "")[:500] if obj.get("response") else "",
                "attack_vector": curl_cmd[:500] if curl_cmd else "",
            }
        )
    return findings


# ── Auto-detect format ───────────────────────────────────────────────────────


def detect_and_parse(data: object, filepath: Path, target_name: str) -> list[dict]:
    if isinstance(data, dict):
        if "@version" in data and "site" in data:
            return parse_zap_json(data, target_name)

    if filepath.suffix == ".jsonl" or filepath.name.startswith("nuclei"):
        return parse_nuclei_jsonl(filepath, target_name)

    print(f"  [warn] Could not detect DAST format for {filepath.name}", file=sys.stderr)
    return []


#: The result file each scanner leaves in the scan directory, by the exact name
#: examples.md tells the agent to write (R3-R5), mapped to the step it is the output of.
#: Only these names, only at the top level of the scan directory, are read: a stale
#: `old/zap-report.json` or a `zap-config.json` holding ZAP-shaped JSON is not evidence
#: that a scanner ran.
RESULT_FILES = {"zap-report.json": "zap", "nuclei-output.jsonl": "nuclei"}


#: Name fragments that make a file in a scan directory look like a result of this mode, so one
#: that is not named exactly as documented is reported as ignored rather than silently skipped.
RESULT_HINTS = ("zap", "nuclei")


def read_result_file(path: Path, target_name: str) -> scan_coverage.Read:
    """Parse one result file into a scan_coverage.Read.

    A zap-report.json counts as ZAP's result only if it has the ZAP report shape, and a
    nuclei-output.jsonl only if every non-empty line is a Nuclei result (an empty file is a
    result: Nuclei found nothing). Raises on a file that cannot be read or parsed (the
    caller names it and the step stays unread).
    """
    expected = RESULT_FILES[path.name]
    decoded = scan_coverage.decode_text(path.read_bytes(), path.name)
    notes = list(decoded.notes)
    if expected == "nuclei":
        findings = parse_nuclei_jsonl(path, target_name, decoded.text)
        problems = nuclei_problems(decoded.text)
        if not problems:
            return scan_coverage.Read("nuclei", findings, list(decoded.degraded), notes)
        more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
        notes.append(f"{path.name} has lines that are not nuclei results: {problems[0]}{more}")
        return scan_coverage.Read(None, findings, [], notes)
    raw = json.loads(decoded.text)
    findings = detect_and_parse(raw, path, target_name)
    if isinstance(raw, dict) and "@version" in raw and "site" in raw:
        return scan_coverage.Read("zap", findings, list(decoded.degraded), notes)
    notes.append(f"{path.name} does not have the ZAP report shape")
    return scan_coverage.Read(None, findings, [], notes)


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
    raw = [
        {
            "target_name": "vendor-portal-web",
            "url": "https://vendor.acme-corp.com/api/vendors",
            "http_method": "POST",
            "rule_id": "DAST-zap-40018",
            "severity": "high",
            "message": "SQL Injection: string concatenation detected in vendor search parameter",
            "cwe": "CWE-89",
            "owasp": "A03:2021",
            "scanner": "zap",
            "parameter": "search",
            "evidence": "vendor' OR '1'='1",
            "attack_vector": "search=vendor' OR '1'='1",
        },
        {
            "target_name": "vendor-portal-web",
            "url": "https://vendor.acme-corp.com/login",
            "http_method": "GET",
            "rule_id": "DAST-zap-10038",
            "severity": "medium",
            "message": "Content Security Policy (CSP) Header Not Set",
            "cwe": "CWE-693",
            "owasp": "A05:2021",
            "scanner": "zap",
            "parameter": "",
            "evidence": "",
            "attack_vector": "",
        },
        {
            "target_name": "vendor-portal-web",
            "url": "https://vendor.acme-corp.com/api/export",
            "http_method": "GET",
            "rule_id": "DAST-zap-40009",
            "severity": "high",
            "message": "Server Side Request Forgery: internal URL accessible via export endpoint",
            "cwe": "CWE-918",
            "owasp": "A10:2021",
            "scanner": "zap",
            "parameter": "url",
            "evidence": "HTTP/1.1 200 OK (internal response)",
            "attack_vector": "url=http://169.254.169.254/latest/meta-data/",
        },
        {
            "target_name": "vendor-portal-web",
            "url": "https://vendor.acme-corp.com",
            "http_method": "",
            "rule_id": "DAST-nuc-tech-detect-flask",
            "severity": "info",
            "message": "Flask technology detected via server header",
            "cwe": "",
            "owasp": "",
            "scanner": "nuclei",
            "parameter": "",
            "evidence": "Server: Werkzeug/2.3.7",
            "attack_vector": "",
        },
        {
            "target_name": "pricing-api-web",
            "url": "https://api.acme-corp.com/v1/prices",
            "http_method": "GET",
            "rule_id": "DAST-zap-40040",
            "severity": "medium",
            "message": "CORS Misconfiguration: wildcard Access-Control-Allow-Origin",
            "cwe": "CWE-942",
            "owasp": "A05:2021",
            "scanner": "zap",
            "parameter": "",
            "evidence": "Access-Control-Allow-Origin: *",
            "attack_vector": "",
        },
        {
            "target_name": "pricing-api-web",
            "url": "https://api.acme-corp.com/.env",
            "http_method": "GET",
            "rule_id": "DAST-nuc-exposure-env",
            "severity": "critical",
            "message": "Exposed .env file containing database credentials",
            "cwe": "CWE-200",
            "owasp": "A01:2021",
            "scanner": "nuclei",
            "parameter": "",
            "evidence": "DB_PASSWORD=...",
            "attack_vector": "",
        },
    ]

    findings = []
    for r in raw:
        fp = _fingerprint(r["target_name"], r["url"], r["rule_id"])
        findings.append(
            {
                "id": fp,
                "repo": r["target_name"],
                "file": r["url"],
                "line": None,
                "rule_id": r["rule_id"],
                "severity": r["severity"],
                "message": r["message"],
                "cwe": r["cwe"],
                "owasp": r["owasp"],
                "scanner": r["scanner"],
                "raw_severity": r["severity"],
                "fingerprint": fp,
                "target_type": "webapp",
                "target_name": r["target_name"],
                "url": r["url"],
                "http_method": r["http_method"],
                "binary_hash": "",
                "parameter": r.get("parameter", ""),
                "response_code": "",
                "evidence": r.get("evidence", ""),
                "attack_vector": r.get("attack_vector", ""),
            }
        )
    return findings


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize DAST scanner outputs (ZAP JSON, Nuclei JSONL)"
    )
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--scans-dir", help="Directory containing DAST result files")
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
        print(f"[parse_dast] Generated {len(findings)} sample DAST findings", file=sys.stderr)
        scan_coverage.report("parse_dast", scan_reports, args.coverage_output)
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
            print(f"[parse_dast] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            scan_coverage.report("parse_dast", scan_reports, args.coverage_output)
            sys.exit(1)

        try:
            candidates = sorted(
                f for f in scans_dir.rglob("*") if f.name in RESULT_FILES and f.is_file()
            )
            all_findings, reports, n_files = scan_coverage.collect(
                "parse_dast",
                scans_dir,
                candidates,
                PLANNED_STEPS,
                read_result_file,
                RESULT_FILES,
                RESULT_HINTS,
            )
        except Exception as exc:  # noqa: BLE001 - never exit without the coverage sidecar
            print(f"[parse_dast] ERROR: reading results failed: {exc}", file=sys.stderr)
            scan_reports.append(
                scan_coverage.unknown_report(
                    str(scans_dir),
                    f"unexpected failure while reading results: {scan_coverage.short(exc)}",
                )
            )
            scan_coverage.report("parse_dast", scan_reports, args.coverage_output)
            sys.exit(1)
        scan_reports.extend(reports)

        if not n_files:
            print(f"[parse_dast] No ZAP/Nuclei result files found in {scans_dir}", file=sys.stderr)
            scan_coverage.report("parse_dast", scan_reports, args.coverage_output)
            sys.exit(1)

        findings = deduplicate(all_findings)
        print(
            f"[parse_dast] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )
        scan_coverage.report("parse_dast", scan_reports, args.coverage_output)

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_dast] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
