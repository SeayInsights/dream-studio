"""
parse_dast.py — DAST result parser and normalizer.

Reads DAST scan results from ~/.dream-studio/security/scans/{client}/
Supports: OWASP ZAP JSON reports, Nuclei JSONL output
Outputs: normalized flat findings list as JSON (stdout or file)

Usage:
    py -3.12 parse_dast.py --client <name> [--scans-dir <path>] [--output <path>]
    py -3.12 parse_dast.py --sample --client <name>
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

ZAP_RISK_MAP = {0: "info", 1: "low", 2: "medium", 3: "high"}

ZAP_CWE_MAP = {
    "10010": "CWE-16",    # Cookie No HttpOnly Flag
    "10011": "CWE-614",   # Cookie Without Secure Flag
    "10012": "CWE-525",   # Password Autocomplete in Browser
    "10015": "CWE-693",   # Re-examine Cache-control Directives
    "10016": "CWE-311",   # Web Browser XSS Protection Not Enabled
    "10017": "CWE-200",   # Cross-Domain JavaScript Source File Inclusion
    "10019": "CWE-16",    # Content-Type Header Missing
    "10020": "CWE-693",   # X-Frame-Options Header
    "10021": "CWE-693",   # X-Content-Type-Options Header Missing
    "10023": "CWE-693",   # Information Disclosure - Debug Error Messages
    "10024": "CWE-539",   # Information Disclosure - Sensitive Info in URL
    "10025": "CWE-200",   # Information Disclosure - Sensitive Info in HTTP Referrer
    "10027": "CWE-200",   # Information Disclosure - Suspicious Comments
    "10028": "CWE-200",   # Open Redirect
    "10029": "CWE-16",    # Cookie Poisoning
    "10030": "CWE-693",   # User Controllable Charset
    "10031": "CWE-693",   # User Controllable HTML Element Attribute
    "10032": "CWE-16",    # Viewstate
    "10033": "CWE-16",    # Directory Browsing
    "10034": "CWE-548",   # Heartbleed OpenSSL Vulnerability
    "10035": "CWE-693",   # Strict-Transport-Security Header
    "10036": "CWE-200",   # Server Leaks Version Information
    "10037": "CWE-200",   # Server Leaks Information via X-Powered-By
    "10038": "CWE-16",    # Content Security Policy (CSP) Header Not Set
    "10039": "CWE-693",   # X-Backend-Server Header Information Leak
    "10040": "CWE-523",   # Secure Pages Include Mixed Content
    "10049": "CWE-16",    # Storable and Cacheable Content
    "10050": "CWE-693",   # Retrieved from Cache
    "10054": "CWE-1275",  # Cookie without SameSite Attribute
    "10055": "CWE-693",   # CSP
    "10096": "CWE-200",   # Timestamp Disclosure
    "10097": "CWE-16",    # Insufficient Site Isolation Against Spectre
    "10098": "CWE-16",    # Cross-Domain Misconfiguration
    "10105": "CWE-16",    # Weak Authentication Method
    "10202": "CWE-200",   # Absence of Anti-CSRF Tokens
    "20012": "CWE-20",    # Anti-CSRF Tokens Check
    "20014": "CWE-20",    # HTTP Parameter Pollution
    "20019": "CWE-16",    # External Redirect
    "30001": "CWE-311",   # Buffer Overflow
    "30002": "CWE-89",    # Format String Error
    "30003": "CWE-22",    # Integer Overflow Error
    "40003": "CWE-352",   # CRLF Injection
    "40008": "CWE-22",    # Path Traversal
    "40009": "CWE-918",   # Server Side Request Forgery
    "40012": "CWE-79",    # Cross Site Scripting (Reflected)
    "40013": "CWE-384",   # Session Fixation
    "40014": "CWE-79",    # Cross Site Scripting (Persistent)
    "40016": "CWE-94",    # Cross Site Scripting (Persistent) - Prime
    "40017": "CWE-79",    # Cross Site Scripting (Persistent) - Spider
    "40018": "CWE-89",    # SQL Injection
    "40019": "CWE-89",    # SQL Injection - MySQL
    "40020": "CWE-89",    # SQL Injection - Hypersonic SQL
    "40021": "CWE-89",    # SQL Injection - Oracle
    "40022": "CWE-89",    # SQL Injection - PostgreSQL
    "40024": "CWE-89",    # SQL Injection - SQLite
    "40026": "CWE-78",    # Cross Site Scripting (DOM Based)
    "40027": "CWE-89",    # SQL Injection - MsSQL
    "40028": "CWE-611",   # ELMAH Information Leak
    "40029": "CWE-209",   # Trace.axd Information Leak
    "40032": "CWE-200",   # .htaccess Information Leak
    "40034": "CWE-200",   # .env Information Leak
    "40035": "CWE-200",   # Hidden File Finder
    "40038": "CWE-200",   # Bypassing 403
    "40039": "CWE-200",   # Web Cache Deception
    "40040": "CWE-942",   # CORS Misconfiguration
    "40042": "CWE-829",   # Spring Actuator Information Leak
    "40043": "CWE-94",    # Log4Shell
    "40044": "CWE-400",   # Exponential Entity Expansion (Billion Laughs)
    "40045": "CWE-94",    # Spring4Shell
    "90001": "CWE-541",   # Insecure JSF ViewState
    "90011": "CWE-16",    # Charset Mismatch
    "90019": "CWE-16",    # Server Side Code Injection
    "90020": "CWE-601",   # Remote OS Command Injection
    "90021": "CWE-79",    # XPath Injection
    "90022": "CWE-209",   # Application Error Disclosure
    "90023": "CWE-611",   # XML External Entity Attack
    "90024": "CWE-94",    # Generic Padding Oracle
    "90025": "CWE-94",    # Expression Language Injection
    "90026": "CWE-78",    # SOAP Action Spoofing
    "90028": "CWE-200",   # Insecure HTTP Method
    "90029": "CWE-200",   # SOAP XML Injection
    "90030": "CWE-200",   # WSDL File Detection
    "90033": "CWE-200",   # Loosely Scoped Cookie
    "90034": "CWE-693",   # Cloud Metadata Potentially Exposed
}

ZAP_OWASP_MAP = {
    "40012": "A03:2021", "40014": "A03:2021", "40016": "A03:2021",
    "40017": "A03:2021", "40026": "A03:2021", "90021": "A03:2021",
    "40018": "A03:2021", "40019": "A03:2021", "40020": "A03:2021",
    "40021": "A03:2021", "40022": "A03:2021", "40024": "A03:2021",
    "40027": "A03:2021", "90019": "A03:2021", "90020": "A03:2021",
    "40003": "A03:2021",
    "40008": "A01:2021", "40009": "A10:2021",
    "10011": "A02:2021", "10054": "A02:2021", "10040": "A02:2021",
    "10038": "A05:2021", "10055": "A05:2021", "10020": "A05:2021",
    "10035": "A05:2021", "10021": "A05:2021", "10016": "A05:2021",
    "10202": "A01:2021", "40013": "A07:2021",
    "40040": "A05:2021", "40043": "A06:2021", "40045": "A06:2021",
    "90023": "A05:2021", "90034": "A05:2021",
}

NUCLEI_SEVERITY_MAP = {
    "critical": "critical", "high": "high", "medium": "medium",
    "low": "low", "info": "info", "unknown": "low",
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
            cwe = f"CWE-{cwe_id}" if cwe_id and str(cwe_id) != "-1" else ZAP_CWE_MAP.get(plugin_id, "")
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
                findings.append({
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
                })
    return findings


# ── Parser: Nuclei JSONL ─────────────────────────────────────────────────────

def parse_nuclei_jsonl(path: Path, target_name: str) -> list[dict]:
    findings = []
    with open(path, encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f"  [warn] Skipping malformed line {line_num} in {path.name}", file=sys.stderr)
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

            findings.append({
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
            })
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
            "url": "https://vendor.plmarketing.com/api/vendors",
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
            "url": "https://vendor.plmarketing.com/login",
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
            "url": "https://vendor.plmarketing.com/api/export",
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
            "url": "https://vendor.plmarketing.com",
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
            "url": "https://api.plmarketing.com/v1/prices",
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
            "url": "https://api.plmarketing.com/.env",
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
        findings.append({
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
        })
    return findings


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and normalize DAST scanner outputs (ZAP JSON, Nuclei JSONL)"
    )
    parser.add_argument("--client", required=True, help="Client name")
    parser.add_argument("--scans-dir", help="Directory containing DAST result files")
    parser.add_argument("--output", help="Output file path. Default: stdout")
    parser.add_argument("--sample", action="store_true", help="Generate synthetic sample findings")
    args = parser.parse_args()

    if args.sample:
        findings = generate_sample()
        print(f"[parse_dast] Generated {len(findings)} sample DAST findings", file=sys.stderr)
    else:
        scans_dir = Path(
            args.scans_dir
            or os.path.expanduser(f"~/.dream-studio/security/scans/{args.client}/")
        )
        if not scans_dir.exists():
            print(f"[parse_dast] ERROR: scans directory not found: {scans_dir}", file=sys.stderr)
            sys.exit(1)

        scan_files = sorted(
            f for f in scans_dir.rglob("*")
            if f.suffix in (".json", ".jsonl") and f.is_file()
            and any(k in f.name.lower() for k in ("zap", "nuclei"))
        )
        if not scan_files:
            print(f"[parse_dast] No ZAP/Nuclei result files found in {scans_dir}", file=sys.stderr)
            sys.exit(1)

        all_findings: list[dict] = []
        for sf in scan_files:
            target_name = sf.parent.parent.name if sf.parent.name.count("-") == 2 else sf.parent.name
            print(f"[parse_dast] Parsing {sf.name} → target={target_name}", file=sys.stderr)
            try:
                if sf.suffix == ".jsonl":
                    parsed = parse_nuclei_jsonl(sf, target_name)
                else:
                    with open(sf, encoding="utf-8") as fh:
                        raw = json.load(fh)
                    parsed = detect_and_parse(raw, sf, target_name)
                print(f"  → {len(parsed)} findings", file=sys.stderr)
                all_findings.extend(parsed)
            except Exception as exc:
                print(f"  [error] Failed to parse {sf.name}: {exc}", file=sys.stderr)

        findings = deduplicate(all_findings)
        print(
            f"[parse_dast] Total: {len(all_findings)} raw → {len(findings)} after dedup",
            file=sys.stderr,
        )

    output_json = json.dumps(findings, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"[parse_dast] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
