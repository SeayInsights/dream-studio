#!/usr/bin/env python3
"""
analyze_netcompat.py — Zscaler/proxy compatibility analysis ETL
Implements TR-007

Usage:
    py -3.12 analyze_netcompat.py --client <name> [--scans-dir <path>]
    py -3.12 analyze_netcompat.py --sample --client plmarketing-kroger

Score formula (per repo, starts at 100, floor 0):
    cert_pinning violation    : -20 per instance
    custom_ssl_context        : -15 per instance
    hardcoded_ca              : -10 per instance
    non_standard_port         : -10 per instance
    websocket_no_tls          : -15 per instance
    custom_dns (Zscaler only) : -10 per instance
    mtls_conflict (Zscaler)   : -20 per instance

Output: ~/.dream-studio/security/datasets/{client}/netcompat.csv
Columns: repo, zscaler_score, cert_pinning, dlp_risk, port_issues, fixes_needed
"""

import argparse
import csv
import json
import pathlib
import sys
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rule ID suffix → finding category mapping
# Matches both {client}-zsc-NNN and {client}-net-NNN patterns
RULE_SUFFIX_MAP: dict[str, str] = {
    "-001": "cert_pinning",
    "-002": "custom_ssl_context",
    "-003": "hardcoded_ca",
    "-004": "non_standard_port",
    "-005": "websocket_no_tls",
    "-006": "custom_dns",
    "-007": "mtls_conflict",
}

# Deduction per instance of each finding category
DEDUCTIONS: dict[str, int] = {
    "cert_pinning": 20,
    "custom_ssl_context": 15,
    "hardcoded_ca": 10,
    "non_standard_port": 10,
    "websocket_no_tls": 15,
    "custom_dns": 10,       # Zscaler only
    "mtls_conflict": 20,    # Zscaler only
}

# Categories that only apply to Zscaler
ZSCALER_ONLY_CATEGORIES: set[str] = {"custom_dns", "mtls_conflict"}

# CSV output columns (in order)
CSV_COLUMNS = ["repo", "zscaler_score", "cert_pinning", "dlp_risk", "port_issues", "fixes_needed"]


# ---------------------------------------------------------------------------
# Sample data generator
# ---------------------------------------------------------------------------

def build_sample_sarif(client_name: str) -> dict:
    """
    Generate a synthetic SARIF dataset with known ZSC findings.
    Covers all seven rule categories across two repos to demonstrate
    the full scoring pipeline.
    """
    prefix = client_name.lower().replace("-", "")

    def result(rule_id: str, repo: str, filepath: str, line: int, level: str, message: str) -> dict:
        return {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": f"{repo}/{filepath}"},
                        "region": {"startLine": line},
                    }
                }
            ],
        }

    results = [
        # repo-alpha: cert pinning (×2) + hardcoded CA (×1) + non-standard port (×1)
        result(f"{prefix}-zsc-001", "repo-alpha", "src/api/client.py", 42, "error",
               "Certificate pinning detected — will break Zscaler SSL inspection."),
        result(f"{prefix}-zsc-001", "repo-alpha", "src/api/legacy.py", 88, "error",
               "Certificate pinning in legacy client — will break Zscaler SSL inspection."),
        result(f"{prefix}-zsc-003", "repo-alpha", "src/utils/ssl_helper.py", 17, "warning",
               "Hardcoded CA bundle path — use REQUESTS_CA_BUNDLE env var instead."),
        result(f"{prefix}-zsc-004", "repo-alpha", "src/integrations/kafka.py", 23, "warning",
               "Outbound connection to non-standard port detected. Port 9092 blocked by Zscaler policy."),

        # repo-beta: websocket (×1) + custom DNS (×2) + mTLS conflict (×1) + custom SSL (×1)
        result(f"{prefix}-zsc-005", "repo-beta", "src/realtime/ws_client.py", 11, "error",
               "Unencrypted WebSocket (ws://) will not work through Zscaler. Replace with wss://."),
        result(f"{prefix}-zsc-006", "repo-beta", "src/dns/resolver.py", 34, "warning",
               "Custom DNS resolution bypasses Zscaler DNS inspection and DLP controls."),
        result(f"{prefix}-zsc-006", "repo-beta", "src/infra/network.py", 5, "warning",
               "socket.gethostbyname() call bypasses Zscaler DNS routing."),
        result(f"{prefix}-zsc-007", "repo-beta", "src/auth/mtls.py", 56, "warning",
               "mTLS client certificate configuration detected — Zscaler SSL inspection breaks mTLS."),
        result(f"{prefix}-zsc-002", "repo-beta", "src/http/session.py", 29, "warning",
               "Custom SSL context with explicit CA bundle loading — include proxy CA or use env vars."),

        # repo-gamma: clean (no findings) — score should stay 100
    ]

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "semgrep",
                        "version": "1.0.0-sample",
                        "rules": [],
                    }
                },
                "results": results,
            }
        ],
    }


def build_sample_profile(client_name: str) -> dict:
    """Generate a synthetic client profile for sample mode."""
    return {
        "client": {
            "name": client_name,
            "github_org": "plmarketing",
        },
        "network": {
            "proxy": {
                "type": "zscaler",
                "ssl_inspection": True,
                "dlp_patterns": ["SSN", "credit_card", "PHI"],
                "blocked_ports": [22, 25, 53, 8080, 9092],
                "custom_ca": "zscaler-root-ca.pem",
            }
        },
        "data": {
            "critical": ["SSN", "credit_card", "PHI", "PII"],
            "sensitive": ["email", "phone", "address", "planogram", "pricing"],
            "pii_patterns": ["\\d{3}-\\d{2}-\\d{4}", "\\d{4}-\\d{4}-\\d{4}-\\d{4}"],
        },
        "stack": {
            "languages": ["python", "javascript", "typescript"],
        },
    }


# ---------------------------------------------------------------------------
# SARIF parsing
# ---------------------------------------------------------------------------

def load_sarif(sarif_path: pathlib.Path) -> list[dict]:
    """Load a SARIF file and return a flat list of result objects."""
    with open(sarif_path, encoding="utf-8") as fh:
        data = json.load(fh)
    results = []
    for run in data.get("runs", []):
        results.extend(run.get("results", []))
    return results


def is_netcompat_rule(rule_id: str) -> bool:
    """
    Return True if the rule ID is a netcompat finding.
    Matches:
      - {anything}-zsc-NNN
      - {anything}-net-NNN
      - ZSC-NNN  (legacy bare form)
      - net-NNN  (legacy bare form)
    """
    rid = rule_id.lower()
    return (
        "-zsc-" in rid
        or "-net-" in rid
        or rid.startswith("zsc-")
        or rid.startswith("net-")
    )


def classify_finding(rule_id: str) -> Optional[str]:
    """
    Map a rule ID to a finding category using the suffix.
    Returns None if the rule ID doesn't match any known pattern.
    """
    rid = rule_id.lower()
    for suffix, category in RULE_SUFFIX_MAP.items():
        if rid.endswith(suffix):
            return category
    return None


def extract_location(result: dict) -> tuple[str, int]:
    """Extract (filepath, line_number) from a SARIF result."""
    try:
        loc = result["locations"][0]["physicalLocation"]
        uri = loc["artifactLocation"]["uri"]
        line = loc.get("region", {}).get("startLine", 0)
        return uri, line
    except (KeyError, IndexError):
        return "unknown", 0


# ---------------------------------------------------------------------------
# DLP risk assessment
# ---------------------------------------------------------------------------

def assess_dlp_risk(findings: list[dict], dlp_terms: list[str]) -> str:
    """
    Cross-reference finding messages and file paths with DLP classification terms.

    Returns:
        'high'   — a data classification term appears in a finding message or file path
        'medium' — a term appears in an adjacent/nearby pattern (heuristic match)
        'low'    — no data terms detected near outbound connections
    """
    if not dlp_terms or not findings:
        return "low"

    lowered_terms = [t.lower() for t in dlp_terms]
    high_hit = False
    medium_hit = False

    for finding in findings:
        message_text = finding.get("message", {}).get("text", "").lower()
        filepath, _ = extract_location(finding)
        filepath_lower = filepath.lower()

        for term in lowered_terms:
            if term in message_text or term in filepath_lower:
                high_hit = True
                break
            # Heuristic: term appears in the file directory but not in the
            # finding message itself — indirect association
            if any(term in part for part in filepath_lower.split("/")):
                medium_hit = True

        if high_hit:
            break

    if high_hit:
        return "high"
    if medium_hit:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_repo(
    repo: str,
    findings: list[dict],
    proxy_type: str,
    dlp_terms: list[str],
) -> dict:
    """
    Calculate the compatibility score for one repo.

    Returns a dict with all CSV column values for this repo.
    """
    # Count findings per category
    counts: dict[str, int] = {cat: 0 for cat in DEDUCTIONS}

    for finding in findings:
        rule_id = finding.get("ruleId", "")
        category = classify_finding(rule_id)
        if category is None:
            continue

        # Suppress Zscaler-only categories when proxy is not Zscaler
        if category in ZSCALER_ONLY_CATEGORIES and proxy_type != "zscaler":
            continue

        counts[category] += 1

    # Score formula: 100 - sum of deductions, floor at 0
    total_deduction = sum(
        DEDUCTIONS[cat] * count for cat, count in counts.items() if count > 0
    )
    score = max(0, 100 - total_deduction)

    # DLP risk
    dlp_risk = assess_dlp_risk(findings, dlp_terms)

    # Port issues = non_standard_port + websocket_no_tls
    port_issues = counts["non_standard_port"] + counts["websocket_no_tls"]

    # Total fixes = sum of all category counts
    fixes_needed = sum(counts.values())

    return {
        "repo": repo,
        "zscaler_score": score,
        "cert_pinning": counts["cert_pinning"],
        "dlp_risk": dlp_risk,
        "port_issues": port_issues,
        "fixes_needed": fixes_needed,
    }


# ---------------------------------------------------------------------------
# Fix recommendations
# ---------------------------------------------------------------------------

FIX_TEMPLATES: dict[str, str] = {
    "cert_pinning": (
        "Remove cert pinning in `{file}:{line}` — "
        "add proxy CA to trust bundle instead (see network.proxy.custom_ca in profile)"
    ),
    "custom_ssl_context": (
        "In `{file}:{line}`, set REQUESTS_CA_BUNDLE env var "
        "instead of loading CA bundle explicitly"
    ),
    "hardcoded_ca": (
        "In `{file}:{line}`, replace hardcoded CA path with "
        "REQUESTS_CA_BUNDLE or SSL_CERT_FILE env var"
    ),
    "non_standard_port": (
        "In `{file}:{line}`, move to port 443 (HTTPS) — "
        "port blocked by {proxy_type} policy"
    ),
    "websocket_no_tls": (
        "In `{file}:{line}`, replace ws:// with wss:// and confirm server supports WSS"
    ),
    "custom_dns": (
        "In `{file}:{line}`, use system DNS (Python default) — "
        "custom resolvers bypass Zscaler DNS inspection"
    ),
    "mtls_conflict": (
        "In `{file}:{line}`, add Zscaler SSL bypass rule for this destination "
        "rather than disabling SSL inspection globally"
    ),
}


def generate_fixes(findings: list[dict], proxy_type: str) -> list[str]:
    """Generate a list of fix recommendation strings for a set of findings."""
    fixes = []
    for finding in findings:
        rule_id = finding.get("ruleId", "")
        category = classify_finding(rule_id)
        if category is None or category not in FIX_TEMPLATES:
            continue
        filepath, line = extract_location(finding)
        template = FIX_TEMPLATES[category]
        fix = template.format(file=filepath, line=line, proxy_type=proxy_type)
        fixes.append(f"[{category}] {fix}")
    return fixes


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_csv(output_path: pathlib.Path, rows: list[dict]) -> None:
    """Write the netcompat CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] for col in CSV_COLUMNS})


def print_summary(rows: list[dict], output_path: pathlib.Path, proxy_type: str) -> None:
    """Print a human-readable summary table to stdout."""
    print(f"\nNetcompat Analysis — proxy_type={proxy_type}")
    print(f"Output: {output_path}\n")
    header = f"{'Repo':<30} {'Score':>6} {'CertPin':>8} {'DLP Risk':>9} {'Ports':>6} {'Fixes':>6}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['repo']:<30} {row['zscaler_score']:>6} "
            f"{row['cert_pinning']:>8} {row['dlp_risk']:>9} "
            f"{row['port_issues']:>6} {row['fixes_needed']:>6}"
        )
    print()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_analysis(
    scans_dir: pathlib.Path,
    profile: dict,
    extra_repos: Optional[list[str]] = None,
) -> list[dict]:
    """
    Core analysis pipeline. Works with ingested SARIF or sample data.

    Args:
        scans_dir:   Root of scans storage: scans_dir/{repo}/{date}/semgrep.sarif
        profile:     Parsed client YAML profile dict.
        extra_repos: Optional list of repo names known to have no findings (score=100).

    Returns:
        List of row dicts (one per repo) ready for CSV output.
    """
    proxy_cfg = profile.get("network", {}).get("proxy", {})
    proxy_type = proxy_cfg.get("type", "none")
    data_cfg = profile.get("data", {})
    dlp_terms: list[str] = (
        data_cfg.get("critical", []) + data_cfg.get("sensitive", [])
    )

    rows: list[dict] = []
    repos_processed: set[str] = set()

    # Walk scans directory looking for per-repo SARIF
    if scans_dir.exists():
        for repo_dir in sorted(scans_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            repo_name = repo_dir.name

            # Pick most recent date subdirectory
            date_dirs = sorted(
                [d for d in repo_dir.iterdir() if d.is_dir()],
                reverse=True,
            )
            if not date_dirs:
                continue
            latest = date_dirs[0]

            sarif_path = latest / "semgrep.sarif"
            if not sarif_path.exists():
                continue

            all_results = load_sarif(sarif_path)
            # Filter to netcompat findings only
            netcompat_findings = [r for r in all_results if is_netcompat_rule(r.get("ruleId", ""))]

            row = score_repo(repo_name, netcompat_findings, proxy_type, dlp_terms)
            rows.append(row)
            repos_processed.add(repo_name)

    # Add any explicitly provided repos with no SARIF (clean score)
    for repo_name in (extra_repos or []):
        if repo_name not in repos_processed:
            rows.append({
                "repo": repo_name,
                "zscaler_score": 100,
                "cert_pinning": 0,
                "dlp_risk": "low",
                "port_issues": 0,
                "fixes_needed": 0,
            })

    return rows


def run_sample_mode(client: str) -> None:
    """
    Generate synthetic SARIF data, run analysis, and write CSV.
    Used for pipeline demonstration and testing.
    """
    print(f"[sample] Generating synthetic SARIF for client={client}")

    profile = build_sample_profile(client)
    proxy_type = profile["network"]["proxy"]["type"]
    dlp_terms = (
        profile["data"]["critical"] + profile["data"]["sensitive"]
    )

    sarif = build_sample_sarif(client)
    all_results = sarif["runs"][0]["results"]

    # Group results by repo (extracted from artifactLocation URI prefix)
    repo_findings: dict[str, list[dict]] = {}
    for result in all_results:
        filepath, _ = extract_location(result)
        # URI format: "{repo}/{rest-of-path}"
        repo = filepath.split("/")[0]
        repo_findings.setdefault(repo, []).append(result)

    # Score each repo that has findings
    rows: list[dict] = []
    for repo, findings in sorted(repo_findings.items()):
        netcompat = [r for r in findings if is_netcompat_rule(r.get("ruleId", ""))]
        row = score_repo(repo, netcompat, proxy_type, dlp_terms)
        rows.append(row)
        print(f"[sample] {repo}: {len(netcompat)} netcompat findings, score={row['zscaler_score']}")

        # Print fixes for visibility
        fixes = generate_fixes(netcompat, proxy_type)
        for fix in fixes:
            print(f"         FIX: {fix}")

    # Add clean repo (no findings, score=100)
    rows.append({
        "repo": "repo-gamma",
        "zscaler_score": 100,
        "cert_pinning": 0,
        "dlp_risk": "low",
        "port_issues": 0,
        "fixes_needed": 0,
    })
    print("[sample] repo-gamma: 0 netcompat findings, score=100")

    output_path = (
        pathlib.Path.home()
        / ".dream-studio"
        / "security"
        / "datasets"
        / client
        / "netcompat.csv"
    )
    write_csv(output_path, rows)
    print_summary(rows, output_path, proxy_type)
    print(f"[sample] CSV written to: {output_path}")
    print("[sample] Pipeline complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zscaler/proxy compatibility analysis ETL (TR-007)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--client",
        required=True,
        help="Client name matching ~/.dream-studio/clients/{client}.yaml",
    )
    parser.add_argument(
        "--scans-dir",
        help=(
            "Root scans directory (default: ~/.dream-studio/security/scans/{client}/). "
            "Layout expected: {scans_dir}/{repo}/{date}/semgrep.sarif"
        ),
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Generate synthetic sample data and run full pipeline (for testing)",
    )
    parser.add_argument(
        "--fixes",
        action="store_true",
        help="Print fix recommendations to stdout in addition to writing CSV",
    )

    args = parser.parse_args()
    client = args.client

    if args.sample:
        run_sample_mode(client)
        return

    # Load client profile
    profile_path = pathlib.Path.home() / ".dream-studio" / "clients" / f"{client}.yaml"
    if not profile_path.exists():
        print(
            f"ERROR: Client profile not found at {profile_path}\n"
            "Run `client-work:intake` to create it.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(profile_path, encoding="utf-8") as fh:
        profile = yaml.safe_load(fh)

    if not profile:
        print(f"ERROR: Client profile at {profile_path} is empty or invalid.", file=sys.stderr)
        sys.exit(1)

    proxy_type = profile.get("network", {}).get("proxy", {}).get("type", "none")

    # Resolve scans directory
    if args.scans_dir:
        scans_dir = pathlib.Path(args.scans_dir)
    else:
        scans_dir = (
            pathlib.Path.home() / ".dream-studio" / "security" / "scans" / client
        )

    if not scans_dir.exists():
        print(
            f"ERROR: Scans directory not found at {scans_dir}\n"
            "Run `scan ingest --client {client} --repo <repo>` to ingest SARIF results first.",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = run_analysis(scans_dir, profile)

    if not rows:
        print(
            f"WARNING: No repos with netcompat SARIF found under {scans_dir}.\n"
            "Ensure semgrep.sarif files exist and netcompat rules have run.",
            file=sys.stderr,
        )

    if args.fixes:
        # Print fix recommendations per repo
        for row in rows:
            repo = row["repo"]
            repo_dir = scans_dir / repo
            if not repo_dir.exists():
                continue
            date_dirs = sorted([d for d in repo_dir.iterdir() if d.is_dir()], reverse=True)
            if not date_dirs:
                continue
            sarif_path = date_dirs[0] / "semgrep.sarif"
            if not sarif_path.exists():
                continue
            all_results = load_sarif(sarif_path)
            netcompat = [r for r in all_results if is_netcompat_rule(r.get("ruleId", ""))]
            fixes = generate_fixes(netcompat, proxy_type)
            if fixes:
                print(f"\n=== Fixes: {repo} ===")
                for fix in fixes:
                    print(f"  {fix}")

    output_path = (
        pathlib.Path.home()
        / ".dream-studio"
        / "security"
        / "datasets"
        / client
        / "netcompat.csv"
    )
    write_csv(output_path, rows)
    print_summary(rows, output_path, proxy_type)


if __name__ == "__main__":
    main()
