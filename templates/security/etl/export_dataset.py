"""
export_dataset.py — Power BI-ready CSV exporter for enriched security findings.

Reads fully enriched findings JSON (scored + compliance-mapped + mitigated)
via stdin or --input. Exports Power BI-ready CSVs and a metadata.json.

Usage:
    py -3.12 export_dataset.py --client <name> [--input <path>] [--output-dir <path>]

Default output-dir: ~/.dream-studio/security/datasets/{client}/

Dependencies: PyYAML (stdlib + yaml + csv only)
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[export_dataset] ERROR: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Default weights (fallback if client profile not found) ────────────────────
DEFAULT_WEIGHTS = {
    "critical": 10,
    "high": 4,
    "medium": 1,
    "low": 0.25,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_client_profile(client: str) -> dict:
    profile_path = Path(os.path.expanduser(f"~/.dream-studio/clients/{client}.yaml"))
    if not profile_path.exists():
        print(
            f"[export_dataset] WARNING: client profile not found at {profile_path}. "
            "Using default weights.",
            file=sys.stderr,
        )
        return {}
    with open(profile_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def compute_org_score(findings: list[dict], weights: dict) -> float:
    """
    Org score = 100 - (sum(finding_count_by_severity × weight) / total_findings), clamped 0-100.
    When there are no findings, score is 100.
    """
    if not findings:
        return 100.0

    total = len(findings)
    penalty_sum = 0.0
    for f in findings:
        sev = f.get("severity", "low")
        w = weights.get(sev, weights.get("low", 0.25))
        penalty_sum += w

    raw_penalty = (penalty_sum / total) * total  # sum of weights
    # Normalize: use a ceiling of total * max_weight to keep scale meaningful
    max_weight = max(weights.values()) if weights else 10
    ceiling = total * max_weight
    penalty_pct = min((raw_penalty / ceiling) * 100, 100) if ceiling > 0 else 0

    score = max(0.0, 100.0 - penalty_pct)
    return round(score, 1)


def safe_str(value) -> str:
    """Convert any value to a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


def write_csv(filepath: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Write a list of dicts to a CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Ensure all fields are present and string-safe
            safe_row = {k: safe_str(row.get(k, "")) for k in fieldnames}
            writer.writerow(safe_row)
    print(f"[export_dataset] Wrote {len(rows)} rows → {filepath}", file=sys.stderr)


# ── CSV generators ────────────────────────────────────────────────────────────

def build_findings_csv(findings: list[dict]) -> list[dict]:
    rows = []
    for f in findings:
        rows.append({
            "id":                 f.get("id", ""),
            "repo":               f.get("repo", ""),
            "file":               f.get("file", ""),
            "line":               f.get("line", ""),
            "rule_id":            f.get("rule_id", ""),
            "severity":           f.get("severity", ""),
            "cvss":               f.get("cvss", ""),
            "business_impact":    f.get("business_impact", ""),
            "risk_score":         f.get("risk_score", ""),
            "owasp":              f.get("owasp", ""),
            "cwe":                f.get("cwe", ""),
            "status":             f.get("status", "open"),
            "age_days":           f.get("age_days", "0"),
            "scanner":            f.get("scanner", ""),
            "message":            f.get("message", ""),
            "compliance_controls": safe_str(f.get("compliance_controls", [])),
        })
    return rows


FINDINGS_FIELDS = [
    "id", "repo", "file", "line", "rule_id", "severity", "cvss",
    "business_impact", "risk_score", "owasp", "cwe", "status",
    "age_days", "scanner", "message", "compliance_controls",
]


def build_mitigations_csv(findings: list[dict]) -> list[dict]:
    rows = []
    for f in findings:
        rows.append({
            "finding_id":        f.get("id", ""),
            "rule_id":           f.get("rule_id", ""),
            "title":             f.get("mitigation_title", ""),
            "immediate_fix":     f.get("immediate_fix", ""),
            "long_term_fix":     f.get("long_term_fix", ""),
            "verification_test": f.get("verification_test", ""),
            "effort_estimate":   f.get("effort_estimate", ""),
            "code_before":       f.get("code_before", ""),
            "code_after":        f.get("code_after", ""),
        })
    return rows


MITIGATIONS_FIELDS = [
    "finding_id", "rule_id", "title", "immediate_fix", "long_term_fix",
    "verification_test", "effort_estimate", "code_before", "code_after",
]


def build_compliance_csv(
    findings: list[dict],
    gaps: list[dict],
) -> list[dict]:
    """
    Build compliance.csv from matched controls and gap controls.
    finding_count = number of findings that matched this control.
    """
    # Count findings per control display_id
    control_finding_counts: dict[str, int] = {}
    control_meta: dict[str, dict] = {}

    for f in findings:
        controls = f.get("compliance_controls", []) or []
        for ctrl in controls:
            control_finding_counts[ctrl] = control_finding_counts.get(ctrl, 0) + 1
            if ctrl not in control_meta:
                # Parse framework and control_id from display_id (e.g. "SOC2-CC6.1")
                parts = ctrl.split("-", 1)
                framework = parts[0] if parts else ctrl
                control_id = parts[1] if len(parts) > 1 else ctrl
                control_meta[ctrl] = {
                    "framework": framework,
                    "control_id": control_id,
                    "title": "",  # title not readily available here
                    "covered_by_scan": "yes",
                    "gap_status": "covered",
                }

    rows = []
    # Covered controls
    for display_id, count in control_finding_counts.items():
        meta = control_meta.get(display_id, {})
        rows.append({
            "framework":       meta.get("framework", ""),
            "control_id":      display_id,
            "title":           meta.get("title", ""),
            "covered_by_scan": "yes",
            "finding_count":   count,
            "gap_status":      "covered",
        })

    # Gap controls
    for gap in gaps:
        rows.append({
            "framework":       gap.get("framework", ""),
            "control_id":      gap.get("display_id", gap.get("control_id", "")),
            "title":           gap.get("title", ""),
            "covered_by_scan": "partial",
            "finding_count":   0,
            "gap_status":      "gap",
        })

    return rows


COMPLIANCE_FIELDS = [
    "framework", "control_id", "title", "covered_by_scan", "finding_count", "gap_status",
]


def build_repos_csv(findings: list[dict], repo_scores: dict) -> list[dict]:
    """Aggregate per-repo statistics."""
    repos: dict[str, dict] = {}
    today = date.today().isoformat()

    for f in findings:
        repo = f.get("repo", "unknown")
        if repo not in repos:
            repos[repo] = {
                "name": repo,
                "language": "",
                "last_scan": today,
                "risk_score": 0.0,
                "finding_count": 0,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
            }
        r = repos[repo]
        r["finding_count"] += 1
        sev = f.get("severity", "low")
        if sev == "critical":
            r["critical_count"] += 1
        elif sev == "high":
            r["high_count"] += 1
        elif sev == "medium":
            r["medium_count"] += 1
        else:
            r["low_count"] += 1

    # Apply risk scores from score_findings output
    for repo, score_info in (repo_scores or {}).items():
        if repo in repos:
            if isinstance(score_info, dict):
                repos[repo]["risk_score"] = score_info.get("score", 0.0)
            else:
                repos[repo]["risk_score"] = score_info

    return list(repos.values())


REPOS_FIELDS = [
    "name", "language", "last_scan", "risk_score",
    "finding_count", "critical_count", "high_count",
]


def build_trends_row(
    findings: list[dict],
    org_score: float,
    existing_trends_path: Path,
) -> list[dict]:
    """
    Build trends.csv. Single row for current scan.
    If the file already exists, append the new row.
    """
    today = date.today().isoformat()
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        if sev in severity_counts:
            severity_counts[sev] += 1

    new_row = {
        "date":           today,
        "total_findings": len(findings),
        "critical":       severity_counts["critical"],
        "high":           severity_counts["high"],
        "medium":         severity_counts["medium"],
        "low":            severity_counts["low"],
        "org_score":      org_score,
        "resolved_count": 0,
    }

    # Read existing trends if file exists
    existing_rows: list[dict] = []
    if existing_trends_path.exists():
        try:
            with open(existing_trends_path, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                existing_rows = list(reader)
        except Exception as exc:
            print(f"[export_dataset] WARNING: Could not read existing trends: {exc}", file=sys.stderr)

    # Replace row for today or append
    updated = [r for r in existing_rows if r.get("date") != today]
    updated.append(new_row)
    return updated


TRENDS_FIELDS = [
    "date", "total_findings", "critical", "high", "medium", "low",
    "org_score", "resolved_count",
]


def build_metadata(
    client_profile: dict,
    findings: list[dict],
    org_score: float,
) -> dict:
    client_info = client_profile.get("client", {})
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    repos: set[str] = set()
    for f in findings:
        sev = f.get("severity", "low")
        if sev in severity_counts:
            severity_counts[sev] += 1
        repos.add(f.get("repo", "unknown"))

    frameworks = client_profile.get("compliance", {}).get("frameworks", [])

    return {
        "client_name":      client_info.get("name", "Unknown"),
        "enterprise":       client_info.get("enterprise", ""),
        "scan_date":        date.today().isoformat(),
        "total_repos":      len(repos),
        "total_findings":   len(findings),
        "severity_counts":  severity_counts,
        "org_score":        org_score,
        "frameworks":       frameworks,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export enriched security findings to Power BI-ready CSVs"
    )
    parser.add_argument("--client", required=True, help="Client name (e.g. plmarketing-kroger)")
    parser.add_argument("--input", help="Path to enriched findings JSON. Default: stdin")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Default: ~/.dream-studio/security/datasets/{client}/",
    )
    args = parser.parse_args()

    # ── Load input ────────────────────────────────────────────────────────────
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"[export_dataset] ERROR: input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        raw_json = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "[export_dataset] ERROR: No --input specified and stdin is a TTY. "
                "Pipe generate_mitigations.py output or pass --input <path>.",
                file=sys.stderr,
            )
            sys.exit(1)
        raw_json = sys.stdin.read()

    try:
        envelope = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[export_dataset] ERROR: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    if isinstance(envelope, list):
        findings = envelope
        gaps: list[dict] = []
        repo_scores: dict = {}
    elif isinstance(envelope, dict):
        findings = envelope.get("findings", [])
        gaps = envelope.get("gaps", [])
        repo_scores = envelope.get("repo_scores", {})
    else:
        print("[export_dataset] ERROR: Expected JSON array or object", file=sys.stderr)
        sys.exit(1)

    print(
        f"[export_dataset] Exporting {len(findings)} findings for client: {args.client}",
        file=sys.stderr,
    )

    # ── Output directory ──────────────────────────────────────────────────────
    output_dir = Path(
        args.output_dir
        or os.path.expanduser(f"~/.dream-studio/security/datasets/{args.client}/")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[export_dataset] Output directory: {output_dir}", file=sys.stderr)

    # ── Load client profile ───────────────────────────────────────────────────
    client_profile = load_client_profile(args.client)
    weights = (
        client_profile
        .get("dashboard", {})
        .get("org_score", {})
        .get("weights", DEFAULT_WEIGHTS)
    )

    # ── Compute org score ─────────────────────────────────────────────────────
    org_score = compute_org_score(findings, weights)
    print(f"[export_dataset] Org score: {org_score}", file=sys.stderr)

    # ── Write findings.csv ────────────────────────────────────────────────────
    findings_rows = build_findings_csv(findings)
    write_csv(output_dir / "findings.csv", findings_rows, FINDINGS_FIELDS)

    # ── Write mitigations.csv ─────────────────────────────────────────────────
    mitigations_rows = build_mitigations_csv(findings)
    write_csv(output_dir / "mitigations.csv", mitigations_rows, MITIGATIONS_FIELDS)

    # ── Write compliance.csv ──────────────────────────────────────────────────
    compliance_rows = build_compliance_csv(findings, gaps)
    write_csv(output_dir / "compliance.csv", compliance_rows, COMPLIANCE_FIELDS)

    # ── Write repos.csv ───────────────────────────────────────────────────────
    repos_rows = build_repos_csv(findings, repo_scores)
    write_csv(output_dir / "repos.csv", repos_rows, REPOS_FIELDS)

    # ── Write trends.csv (append if exists) ───────────────────────────────────
    trends_path = output_dir / "trends.csv"
    trends_rows = build_trends_row(findings, org_score, trends_path)
    write_csv(trends_path, trends_rows, TRENDS_FIELDS)

    # ── Write metadata.json ───────────────────────────────────────────────────
    metadata = build_metadata(client_profile, findings, org_score)
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[export_dataset] Wrote metadata.json → {metadata_path}", file=sys.stderr)

    # ── Check for existing netcompat.csv (passthrough) ────────────────────────
    netcompat_path = output_dir / "netcompat.csv"
    if netcompat_path.exists():
        print(f"[export_dataset] netcompat.csv already exists at {netcompat_path} — preserved", file=sys.stderr)
    else:
        print(f"[export_dataset] netcompat.csv not found — skipping (run analyze_netcompat.py to generate)", file=sys.stderr)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(
        f"[export_dataset] Done. Files written to {output_dir}:\n"
        f"  findings.csv ({len(findings_rows)} rows)\n"
        f"  mitigations.csv ({len(mitigations_rows)} rows)\n"
        f"  compliance.csv ({len(compliance_rows)} rows)\n"
        f"  repos.csv ({len(repos_rows)} rows)\n"
        f"  trends.csv ({len(trends_rows)} rows)\n"
        f"  metadata.json (org_score={org_score})",
        file=sys.stderr,
    )

    # Emit metadata to stdout so pipeline callers can inspect it
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
